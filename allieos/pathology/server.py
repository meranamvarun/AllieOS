"""Small local web/API server for the AllieOS pathology workflow."""

from __future__ import annotations

import argparse
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable
from urllib.parse import parse_qs, quote, urlparse

from .store import PathologyError, PathologyStore


MAX_REQUEST_BYTES = 1_048_576


def _viewer_url(template: str | None, slide: dict[str, Any]) -> str | None:
    if slide.get("image_uri"):
        return slide["image_uri"]
    if not template or not slide.get("study_instance_uid"):
        return None
    values = {
        key: quote(str(slide.get(key) or ""), safe="")
        for key in ("study_instance_uid", "series_instance_uid", "sop_instance_uid")
    }
    return template.format(**values)


def _page(title: str, body: str) -> bytes:
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{escape(title)} · AllieOS Pathology</title>
<style>
:root {{ color-scheme: light; font: 16px/1.45 system-ui, sans-serif; background:#f5f2ed; color:#292321 }}
body {{ margin:0 }} header {{ background:#5b1f2d; color:white; padding:1rem 5vw }}
main {{ max-width:1100px; margin:2rem auto; padding:0 1.2rem }}
.notice {{ border-left:4px solid #a56b35; background:#fff8e8; padding:.8rem 1rem; margin:1rem 0 }}
.card {{ background:white; border:1px solid #ddd2cb; border-radius:10px; padding:1rem; margin:.8rem 0 }}
table {{ width:100%; border-collapse:collapse; background:white }} th,td {{ text-align:left; padding:.65rem; border-bottom:1px solid #e4ddd8 }}
input,select,textarea,button {{ font:inherit; padding:.55rem; border:1px solid #9d918a; border-radius:6px }}
input[type=search] {{ width:min(38rem, 75vw) }} button {{ background:#5b1f2d; color:white; cursor:pointer }}
a {{ color:#7d243b }} .muted {{ color:#6e625e }} .pill {{ padding:.15rem .5rem; border-radius:1rem; background:#eee7e2 }}
</style></head><body><header><strong>AllieOS Pathology</strong></header><main>
<div class="notice"><strong>Evaluation software:</strong> not validated for diagnostic use. Access must be protected by an institutional identity-aware reverse proxy.</div>
{body}</main></body></html>"""
    return document.encode("utf-8")


class PathologyHandler(BaseHTTPRequestHandler):
    server_version = "AllieOSPathology/0.1"
    store: PathologyStore
    viewer_template: str | None = None

    def log_message(self, format: str, *args: Any) -> None:
        # Never put paths, queries, patient identifiers, or request bodies in logs.
        self.log_request(self.command, self.responses.get(getattr(self, "_last_status", 0), ("",))[0])

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        return

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self._last_status = int(status)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: HTTPStatus, data: Any) -> None:
        self._send(status, json.dumps(data, indent=2).encode("utf-8"), "application/json; charset=utf-8")

    def _actor(self) -> str:
        return self.headers.get("X-Remote-User", "local-evaluation-user")[:200]

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise PathologyError("invalid content length") from error
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise PathologyError("request body is empty or too large")
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            raise PathologyError("Content-Type must be application/json")
        try:
            value = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as error:
            raise PathologyError("invalid JSON") from error
        if not isinstance(value, dict):
            raise PathologyError("JSON body must be an object")
        return value

    def _route_error(self, error: Exception) -> None:
        if isinstance(error, PathologyError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        elif isinstance(error, sqlite3.IntegrityError):
            self._json(HTTPStatus.CONFLICT, {"error": "record conflicts with existing data or references"})
        else:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal server error"})

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/healthz":
                self._json(HTTPStatus.OK, {"status": "ok", "audit_chain_valid": self.store.verify_audit_chain()})
                return
            if parsed.path == "/api/search":
                params = parse_qs(parsed.query)
                self._json(
                    HTTPStatus.OK,
                    self.store.search(
                        params.get("q", [""])[0],
                        doctor_id=params.get("doctor_id", [None])[0],
                        status=params.get("status", [None])[0],
                    ),
                )
                return
            if parsed.path.startswith("/api/patients/"):
                self._json(HTTPStatus.OK, self.store.get_patient(parsed.path.rsplit("/", 1)[-1]))
                return
            if parsed.path.startswith("/api/cases/"):
                data = self.store.get_case(parsed.path.rsplit("/", 1)[-1])
                for specimen in data["specimens"]:
                    for block in specimen["blocks"]:
                        for slide in block["slides"]:
                            slide["viewer_url"] = _viewer_url(self.viewer_template, slide)
                self._json(HTTPStatus.OK, data)
                return
            if parsed.path.startswith("/cases/"):
                self._case_page(parsed.path.rsplit("/", 1)[-1])
                return
            if parsed.path.startswith("/patients/"):
                self._patient_page(parsed.path.rsplit("/", 1)[-1])
                return
            if parsed.path == "/":
                self._search_page(parse_qs(parsed.query).get("q", [""])[0])
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except Exception as error:
            self._route_error(error)

    def do_POST(self) -> None:
        routes: dict[str, Callable[[dict[str, Any], str], Any]] = {
            "/api/patients": lambda b, a: {
                "id": self.store.create_patient(
                    b.get("mrn"), b.get("display_name"), date_of_birth=b.get("date_of_birth"),
                    sex=b.get("sex"), metadata=b.get("metadata"), actor=a
                )
            },
            "/api/doctors": lambda b, a: {
                "id": self.store.create_doctor(
                    b.get("display_name"), external_id=b.get("external_id"), email=b.get("email"), actor=a
                )
            },
            "/api/cases": lambda b, a: {
                "id": self.store.create_case(
                    b.get("accession_number"), b.get("patient_id"), assigned_doctor_id=b.get("assigned_doctor_id"),
                    referring_doctor=b.get("referring_doctor"), organ=b.get("organ"),
                    clinical_history=b.get("clinical_history"), actor=a
                )
            },
            "/api/specimens": lambda b, a: {
                "id": self.store.add_specimen(
                    b.get("case_id"), b.get("label"), site=b.get("site"), procedure=b.get("procedure"), actor=a
                )
            },
            "/api/blocks": lambda b, a: {
                "id": self.store.add_block(b.get("specimen_id"), b.get("label"), actor=a)
            },
            "/api/slides": lambda b, a: {
                "id": self.store.add_slide(
                    b.get("block_id"), b.get("label"), stain=b.get("stain"), image_uri=b.get("image_uri"),
                    study_instance_uid=b.get("study_instance_uid"), series_instance_uid=b.get("series_instance_uid"),
                    sop_instance_uid=b.get("sop_instance_uid"), actor=a
                )
            },
            "/api/reports/draft": lambda b, a: dict(
                zip(
                    ("report_id", "version"),
                    self.store.save_report_draft(
                        b.get("case_id"), b.get("author_id"), b.get("diagnosis"),
                        microscopic_description=b.get("microscopic_description", ""),
                        comment=b.get("comment", ""), actor=a
                    ),
                )
            ),
            "/api/reports/sign": lambda b, a: {
                "version": self.store.sign_report(b.get("case_id"), b.get("doctor_id"), actor=a)
            },
            "/api/reports/amend": lambda b, a: {
                "version": self.store.amend_report(
                    b.get("case_id"), b.get("author_id"), b.get("diagnosis"), b.get("change_reason"),
                    microscopic_description=b.get("microscopic_description", ""),
                    comment=b.get("comment", ""), actor=a
                )
            },
        }
        try:
            handler = routes.get(urlparse(self.path).path)
            if not handler:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            self._json(HTTPStatus.CREATED, handler(self._body(), self._actor()))
        except Exception as error:
            self._route_error(error)

    def _search_page(self, query: str) -> None:
        rows = self.store.search(query) if query else []
        result_rows = "".join(
            f"<tr><td><a href='/cases/{escape(row['case_id'])}'>{escape(row['accession_number'])}</a></td>"
            f"<td>{escape(row['mrn'])}</td><td><a href='/patients/{escape(row['patient_id'])}'>{escape(row['display_name'])}</a></td>"
            f"<td>{escape(row.get('doctor_name') or 'Unassigned')}</td>"
            f"<td><span class='pill'>{escape(row['status'])}</span></td>"
            f"<td>{escape(row.get('diagnosis') or '')}</td></tr>"
            for row in rows
        )
        body = f"""<h1>Case archive</h1>
<form method="get"><label for="q">Search patient metadata, accession, doctor, organ, or diagnosis</label><br>
<input id="q" name="q" type="search" value="{escape(query)}" autocomplete="off">
<button type="submit">Search</button></form>
<p class="muted">{len(rows)} result(s)</p>
<table><thead><tr><th>Accession</th><th>MRN</th><th>Patient</th><th>Doctor</th><th>Status</th><th>Diagnosis</th></tr></thead>
<tbody>{result_rows}</tbody></table>"""
        self._send(HTTPStatus.OK, _page("Case archive", body), "text/html; charset=utf-8")

    def _patient_page(self, patient_id: str) -> None:
        patient = self.store.get_patient(patient_id)
        case_cards = []
        for case in patient["cases"]:
            slide_rows = []
            for slide in case["slides"]:
                url = _viewer_url(self.viewer_template, slide)
                action = f"<a href='{escape(url)}' rel='noreferrer'>Open image</a>" if url else "Archived"
                slide_rows.append(
                    f"<tr><td>{escape(slide['specimen_label'])}</td><td>{escape(slide['block_label'])}</td>"
                    f"<td>{escape(slide['label'])}</td><td>{escape(slide.get('stain') or '')}</td><td>{action}</td></tr>"
                )
            case_cards.append(
                f"<div class='card'><h2><a href='/cases/{escape(case['id'])}'>{escape(case['accession_number'])}</a></h2>"
                f"<p>{escape(case.get('organ') or 'Organ not recorded')} · "
                f"{escape(case.get('assigned_doctor_name') or 'Unassigned')} · "
                f"<span class='pill'>{escape(case['status'])}</span></p>"
                f"<p><strong>Diagnosis:</strong> {escape(case.get('current_diagnosis') or 'Not reported')}</p>"
                f"<table><thead><tr><th>Specimen</th><th>Block</th><th>Slide</th><th>Stain</th><th>Image</th></tr></thead>"
                f"<tbody>{''.join(slide_rows)}</tbody></table></div>"
            )
        body = (
            f"<p><a href='/'>← Search</a></p><h1>{escape(patient['display_name'])}</h1>"
            f"<p>MRN {escape(patient['mrn'])}</p><h2>Pathology history and slides</h2>"
            f"{''.join(case_cards) or '<p>No pathology cases.</p>'}"
        )
        self._send(HTTPStatus.OK, _page(patient["display_name"], body), "text/html; charset=utf-8")

    def _case_page(self, case_id: str) -> None:
        data = self.store.get_case(case_id)
        slides = []
        for specimen in data["specimens"]:
            for block in specimen["blocks"]:
                for slide in block["slides"]:
                    url = _viewer_url(self.viewer_template, slide)
                    action = f"<a href='{escape(url)}' rel='noreferrer'>Open image</a>" if url else "Archived"
                    slides.append(
                        f"<tr><td>{escape(specimen['label'])}</td><td>{escape(block['label'])}</td>"
                        f"<td>{escape(slide['label'])}</td><td>{escape(slide.get('stain') or '')}</td><td>{action}</td></tr>"
                    )
        versions = []
        if data["report"]:
            for version in data["report"]["versions"]:
                versions.append(
                    f"<div class='card'><strong>Version {version['version']} · {escape(version['state'])}</strong> "
                    f"<span class='muted'>by {escape(version['author_name'])} at {escape(version['created_at'])}</span>"
                    f"<h3>Diagnosis</h3><p>{escape(version['diagnosis'])}</p>"
                    f"<h3>Microscopy</h3><p>{escape(version['microscopic_description'])}</p>"
                    f"{('<p><strong>Reason:</strong> ' + escape(version['change_reason']) + '</p>') if version['change_reason'] else ''}</div>"
                )
        body = f"""<p><a href="/">← Search</a></p><h1>{escape(data['accession_number'])}</h1>
<div class="card"><strong>{escape(data['patient_name'])}</strong> · MRN {escape(data['mrn'])}<br>
{escape(data.get('organ') or 'Organ not recorded')} · {escape(data.get('assigned_doctor_name') or 'Unassigned')} ·
<span class="pill">{escape(data['status'])}</span></div>
<h2>Slides</h2><table><thead><tr><th>Specimen</th><th>Block</th><th>Slide</th><th>Stain</th><th>Image</th></tr></thead>
<tbody>{''.join(slides)}</tbody></table><h2>Report history</h2>{''.join(versions) or '<p>No report drafted.</p>'}"""
        self._send(HTTPStatus.OK, _page(data["accession_number"], body), "text/html; charset=utf-8")


def build_handler(store: PathologyStore, viewer_template: str | None = None) -> type[PathologyHandler]:
    class ConfiguredHandler(PathologyHandler):
        pass

    ConfiguredHandler.store = store
    ConfiguredHandler.viewer_template = viewer_template
    return ConfiguredHandler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="allie-pathology", description="Run the AllieOS pathology workflow service")
    parser.add_argument("--database", type=Path, default=Path("pathology.db"))
    parser.add_argument("--host", default="127.0.0.1", help="listen address; use a protected reverse proxy for remote access")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument(
        "--viewer-url-template",
        help="viewer deep-link template with {study_instance_uid}, {series_instance_uid}, and {sop_instance_uid}",
    )
    parser.add_argument("--initialize-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = PathologyStore(args.database)
    store.initialize()
    if args.initialize_only:
        print(f"Initialized {args.database}")
        return 0
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Refusing direct remote binding; place the service behind an authenticated reverse proxy")
    server = ThreadingHTTPServer((args.host, args.port), build_handler(store, args.viewer_url_template))
    print(f"AllieOS Pathology evaluation service: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""SQLite persistence and domain rules for pathology cases."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator
from urllib.parse import urlparse
import uuid


class PathologyError(ValueError):
    """Raised when a pathology workflow operation is invalid."""


CASE_STATUSES = {"draft", "in_review", "final", "amended"}
REPORT_STATUSES = {"draft", "signed", "amended"}


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS patients (
    id TEXT PRIMARY KEY,
    mrn TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    date_of_birth TEXT,
    sex TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS doctors (
    id TEXT PRIMARY KEY,
    external_id TEXT UNIQUE,
    display_name TEXT NOT NULL,
    email TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    accession_number TEXT NOT NULL UNIQUE,
    patient_id TEXT NOT NULL REFERENCES patients(id),
    assigned_doctor_id TEXT REFERENCES doctors(id),
    referring_doctor TEXT,
    organ TEXT,
    clinical_history TEXT,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'in_review', 'final', 'amended')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS specimens (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE RESTRICT,
    label TEXT NOT NULL,
    site TEXT,
    procedure TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(case_id, label)
);

CREATE TABLE IF NOT EXISTS blocks (
    id TEXT PRIMARY KEY,
    specimen_id TEXT NOT NULL REFERENCES specimens(id) ON DELETE RESTRICT,
    label TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(specimen_id, label)
);

CREATE TABLE IF NOT EXISTS slides (
    id TEXT PRIMARY KEY,
    block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE RESTRICT,
    label TEXT NOT NULL,
    stain TEXT,
    image_uri TEXT,
    study_instance_uid TEXT,
    series_instance_uid TEXT,
    sop_instance_uid TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(block_id, label),
    CHECK (image_uri IS NOT NULL OR sop_instance_uid IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL UNIQUE REFERENCES cases(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'signed', 'amended')),
    current_version INTEGER NOT NULL DEFAULT 0,
    signed_by TEXT REFERENCES doctors(id),
    signed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_versions (
    id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL REFERENCES reports(id) ON DELETE RESTRICT,
    version INTEGER NOT NULL,
    author_id TEXT NOT NULL REFERENCES doctors(id),
    diagnosis TEXT NOT NULL,
    microscopic_description TEXT NOT NULL DEFAULT '',
    comment TEXT NOT NULL DEFAULT '',
    change_reason TEXT,
    state TEXT NOT NULL CHECK (state IN ('draft', 'signed', 'amended')),
    created_at TEXT NOT NULL,
    UNIQUE(report_id, version)
);

CREATE TABLE IF NOT EXISTS audit_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    occurred_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    details_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_cases_patient ON cases(patient_id);
CREATE INDEX IF NOT EXISTS idx_cases_doctor ON cases(assigned_doctor_id);
CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
CREATE INDEX IF NOT EXISTS idx_slides_uids
    ON slides(study_instance_uid, series_instance_uid, sop_instance_uid);
CREATE INDEX IF NOT EXISTS idx_reports_case ON reports(case_id);
CREATE INDEX IF NOT EXISTS idx_report_versions_diagnosis ON report_versions(diagnosis);

CREATE TRIGGER IF NOT EXISTS report_versions_no_update
BEFORE UPDATE ON report_versions BEGIN
    SELECT RAISE(ABORT, 'report versions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS report_versions_no_delete
BEFORE DELETE ON report_versions BEGIN
    SELECT RAISE(ABORT, 'report versions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS audit_events_no_update
BEFORE UPDATE ON audit_events BEGIN
    SELECT RAISE(ABORT, 'audit events are immutable');
END;

CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
BEFORE DELETE ON audit_events BEGIN
    SELECT RAISE(ABORT, 'audit events are immutable');
END;
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _id() -> str:
    return str(uuid.uuid4())


def _required(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PathologyError(f"{field} is required")
    return value.strip()


class PathologyStore:
    """Transactional store for the patient-to-report workflow."""

    def __init__(self, database: str | Path):
        self.database = str(database)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        if self.database != ":memory:":
            Path(self.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            row = connection.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                connection.execute("INSERT INTO schema_version(version) VALUES (1)")
            elif row["version"] != 1:
                raise PathologyError(f"unsupported database schema: {row['version']}")

    def _audit(
        self,
        connection: sqlite3.Connection,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        occurred_at = _now()
        event_id = _id()
        details_json = json.dumps(details or {}, sort_keys=True, separators=(",", ":"))
        last = connection.execute(
            "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = last["event_hash"] if last else "0" * 64
        canonical = "|".join(
            [previous_hash, event_id, occurred_at, actor, action, entity_type, entity_id, details_json]
        )
        event_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        connection.execute(
            """INSERT INTO audit_events
               (id, occurred_at, actor, action, entity_type, entity_id,
                details_json, previous_hash, event_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                occurred_at,
                actor,
                action,
                entity_type,
                entity_id,
                details_json,
                previous_hash,
                event_hash,
            ),
        )

    def create_patient(
        self,
        mrn: str,
        display_name: str,
        *,
        date_of_birth: str | None = None,
        sex: str | None = None,
        metadata: dict[str, Any] | None = None,
        actor: str,
    ) -> str:
        patient_id, created_at = _id(), _now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO patients
                   (id, mrn, display_name, date_of_birth, sex, metadata_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    patient_id,
                    _required(mrn, "mrn"),
                    _required(display_name, "display_name"),
                    date_of_birth,
                    sex,
                    json.dumps(metadata or {}, sort_keys=True),
                    created_at,
                ),
            )
            self._audit(connection, actor, "patient.created", "patient", patient_id, {"mrn": mrn})
        return patient_id

    def create_doctor(
        self,
        display_name: str,
        *,
        external_id: str | None = None,
        email: str | None = None,
        actor: str,
    ) -> str:
        doctor_id, created_at = _id(), _now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO doctors
                   (id, external_id, display_name, email, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (doctor_id, external_id, _required(display_name, "display_name"), email, created_at),
            )
            self._audit(connection, actor, "doctor.created", "doctor", doctor_id)
        return doctor_id

    def create_case(
        self,
        accession_number: str,
        patient_id: str,
        *,
        assigned_doctor_id: str | None = None,
        referring_doctor: str | None = None,
        organ: str | None = None,
        clinical_history: str | None = None,
        actor: str,
    ) -> str:
        case_id, timestamp = _id(), _now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO cases
                   (id, accession_number, patient_id, assigned_doctor_id,
                    referring_doctor, organ, clinical_history, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    case_id,
                    _required(accession_number, "accession_number"),
                    _required(patient_id, "patient_id"),
                    assigned_doctor_id,
                    referring_doctor,
                    organ,
                    clinical_history,
                    timestamp,
                    timestamp,
                ),
            )
            self._audit(
                connection,
                actor,
                "case.created",
                "case",
                case_id,
                {"accession_number": accession_number},
            )
        return case_id

    def add_specimen(
        self,
        case_id: str,
        label: str,
        *,
        site: str | None = None,
        procedure: str | None = None,
        actor: str,
    ) -> str:
        specimen_id = _id()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO specimens(id, case_id, label, site, procedure, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (specimen_id, case_id, _required(label, "label"), site, procedure, _now()),
            )
            self._audit(connection, actor, "specimen.created", "specimen", specimen_id)
        return specimen_id

    def add_block(self, specimen_id: str, label: str, *, actor: str) -> str:
        block_id = _id()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO blocks(id, specimen_id, label, created_at) VALUES (?, ?, ?, ?)",
                (block_id, specimen_id, _required(label, "label"), _now()),
            )
            self._audit(connection, actor, "block.created", "block", block_id)
        return block_id

    def add_slide(
        self,
        block_id: str,
        label: str,
        *,
        stain: str | None = None,
        image_uri: str | None = None,
        study_instance_uid: str | None = None,
        series_instance_uid: str | None = None,
        sop_instance_uid: str | None = None,
        actor: str,
    ) -> str:
        if not image_uri and not sop_instance_uid:
            raise PathologyError("image_uri or sop_instance_uid is required")
        if image_uri and urlparse(image_uri).scheme not in {"http", "https"}:
            raise PathologyError("image_uri must use http or https")
        slide_id = _id()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO slides
                   (id, block_id, label, stain, image_uri, study_instance_uid,
                    series_instance_uid, sop_instance_uid, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    slide_id,
                    block_id,
                    _required(label, "label"),
                    stain,
                    image_uri,
                    study_instance_uid,
                    series_instance_uid,
                    sop_instance_uid,
                    _now(),
                ),
            )
            self._audit(connection, actor, "slide.linked", "slide", slide_id)
        return slide_id

    def save_report_draft(
        self,
        case_id: str,
        author_id: str,
        diagnosis: str,
        *,
        microscopic_description: str = "",
        comment: str = "",
        actor: str,
    ) -> tuple[str, int]:
        timestamp = _now()
        with self.connect() as connection:
            report = connection.execute("SELECT * FROM reports WHERE case_id = ?", (case_id,)).fetchone()
            if report and report["status"] in {"signed", "amended"}:
                raise PathologyError("finalized reports cannot be overwritten; create an amendment")
            if report:
                report_id = report["id"]
                version = report["current_version"] + 1
            else:
                report_id, version = _id(), 1
                connection.execute(
                    """INSERT INTO reports
                       (id, case_id, status, current_version, created_at, updated_at)
                       VALUES (?, ?, 'draft', 0, ?, ?)""",
                    (report_id, case_id, timestamp, timestamp),
                )
            connection.execute(
                """INSERT INTO report_versions
                   (id, report_id, version, author_id, diagnosis,
                    microscopic_description, comment, state, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?)""",
                (
                    _id(),
                    report_id,
                    version,
                    author_id,
                    _required(diagnosis, "diagnosis"),
                    microscopic_description,
                    comment,
                    timestamp,
                ),
            )
            connection.execute(
                "UPDATE reports SET current_version = ?, updated_at = ? WHERE id = ?",
                (version, timestamp, report_id),
            )
            connection.execute(
                "UPDATE cases SET status = 'in_review', updated_at = ? WHERE id = ?",
                (timestamp, case_id),
            )
            self._audit(
                connection,
                actor,
                "report.draft_saved",
                "report",
                report_id,
                {"version": version},
            )
        return report_id, version

    def sign_report(self, case_id: str, doctor_id: str, *, actor: str) -> int:
        timestamp = _now()
        with self.connect() as connection:
            report = connection.execute("SELECT * FROM reports WHERE case_id = ?", (case_id,)).fetchone()
            if not report or report["current_version"] == 0:
                raise PathologyError("a draft report is required before sign-out")
            if report["status"] != "draft":
                raise PathologyError("only a draft report can be signed")
            source = connection.execute(
                """SELECT * FROM report_versions
                   WHERE report_id = ? AND version = ?""",
                (report["id"], report["current_version"]),
            ).fetchone()
            version = report["current_version"] + 1
            connection.execute(
                """INSERT INTO report_versions
                   (id, report_id, version, author_id, diagnosis,
                    microscopic_description, comment, state, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'signed', ?)""",
                (
                    _id(),
                    report["id"],
                    version,
                    doctor_id,
                    source["diagnosis"],
                    source["microscopic_description"],
                    source["comment"],
                    timestamp,
                ),
            )
            connection.execute(
                """UPDATE reports SET status = 'signed', current_version = ?,
                   signed_by = ?, signed_at = ?, updated_at = ? WHERE id = ?""",
                (version, doctor_id, timestamp, timestamp, report["id"]),
            )
            connection.execute(
                "UPDATE cases SET status = 'final', updated_at = ? WHERE id = ?",
                (timestamp, case_id),
            )
            self._audit(
                connection,
                actor,
                "report.signed",
                "report",
                report["id"],
                {"version": version, "doctor_id": doctor_id},
            )
        return version

    def amend_report(
        self,
        case_id: str,
        author_id: str,
        diagnosis: str,
        change_reason: str,
        *,
        microscopic_description: str = "",
        comment: str = "",
        actor: str,
    ) -> int:
        timestamp = _now()
        with self.connect() as connection:
            report = connection.execute("SELECT * FROM reports WHERE case_id = ?", (case_id,)).fetchone()
            if not report or report["status"] not in {"signed", "amended"}:
                raise PathologyError("only a signed report can be amended")
            version = report["current_version"] + 1
            connection.execute(
                """INSERT INTO report_versions
                   (id, report_id, version, author_id, diagnosis,
                    microscopic_description, comment, change_reason, state, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'amended', ?)""",
                (
                    _id(),
                    report["id"],
                    version,
                    author_id,
                    _required(diagnosis, "diagnosis"),
                    microscopic_description,
                    comment,
                    _required(change_reason, "change_reason"),
                    timestamp,
                ),
            )
            connection.execute(
                """UPDATE reports SET status = 'amended', current_version = ?,
                   signed_by = ?, signed_at = ?, updated_at = ? WHERE id = ?""",
                (version, author_id, timestamp, timestamp, report["id"]),
            )
            connection.execute(
                "UPDATE cases SET status = 'amended', updated_at = ? WHERE id = ?",
                (timestamp, case_id),
            )
            self._audit(
                connection,
                actor,
                "report.amended",
                "report",
                report["id"],
                {"version": version, "reason": change_reason},
            )
        return version

    @staticmethod
    def _rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def search(
        self,
        query: str = "",
        *,
        doctor_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if status and status not in CASE_STATUSES:
            raise PathologyError(f"invalid case status: {status}")
        limit = max(1, min(int(limit), 500))
        pattern = f"%{query.strip()}%"
        filters = [
            "(p.mrn LIKE ? OR p.display_name LIKE ? OR c.accession_number LIKE ? "
            "OR COALESCE(c.organ, '') LIKE ? OR COALESCE(c.referring_doctor, '') LIKE ? "
            "OR COALESCE(d.display_name, '') LIKE ? OR COALESCE(rv.diagnosis, '') LIKE ? "
            "OR p.metadata_json LIKE ?)"
        ]
        parameters: list[Any] = [pattern] * 8
        if doctor_id:
            filters.append("c.assigned_doctor_id = ?")
            parameters.append(doctor_id)
        if status:
            filters.append("c.status = ?")
            parameters.append(status)
        parameters.append(limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"""SELECT c.id AS case_id, c.accession_number, c.status, c.organ,
                           c.created_at, p.id AS patient_id, p.mrn, p.display_name,
                           d.id AS doctor_id, d.display_name AS doctor_name,
                           rv.diagnosis
                    FROM cases c
                    JOIN patients p ON p.id = c.patient_id
                    LEFT JOIN doctors d ON d.id = c.assigned_doctor_id
                    LEFT JOIN reports r ON r.case_id = c.id
                    LEFT JOIN report_versions rv
                      ON rv.report_id = r.id AND rv.version = r.current_version
                    WHERE {' AND '.join(filters)}
                    ORDER BY c.updated_at DESC LIMIT ?""",
                parameters,
            ).fetchall()
        return self._rows(rows)

    def get_patient(self, patient_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            patient = connection.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
            if not patient:
                raise PathologyError("patient not found")
            result = dict(patient)
            result["metadata"] = json.loads(result.pop("metadata_json"))
            cases = self._rows(
                connection.execute(
                    """SELECT c.*, d.display_name AS assigned_doctor_name,
                              rv.diagnosis AS current_diagnosis
                       FROM cases c LEFT JOIN doctors d ON d.id = c.assigned_doctor_id
                       LEFT JOIN reports r ON r.case_id = c.id
                       LEFT JOIN report_versions rv
                         ON rv.report_id = r.id AND rv.version = r.current_version
                       WHERE c.patient_id = ? ORDER BY c.created_at DESC""",
                    (patient_id,),
                ).fetchall()
            )
            for case in cases:
                case["slides"] = self._rows(
                    connection.execute(
                        """SELECT sl.*, b.label AS block_label, sp.label AS specimen_label
                           FROM slides sl
                           JOIN blocks b ON b.id = sl.block_id
                           JOIN specimens sp ON sp.id = b.specimen_id
                           WHERE sp.case_id = ? ORDER BY sp.label, b.label, sl.label""",
                        (case["id"],),
                    ).fetchall()
                )
            result["cases"] = cases
            return result

    def get_case(self, case_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            case = connection.execute(
                """SELECT c.*, p.mrn, p.display_name AS patient_name,
                          d.display_name AS assigned_doctor_name
                   FROM cases c JOIN patients p ON p.id = c.patient_id
                   LEFT JOIN doctors d ON d.id = c.assigned_doctor_id WHERE c.id = ?""",
                (case_id,),
            ).fetchone()
            if not case:
                raise PathologyError("case not found")
            result = dict(case)
            specimens = self._rows(
                connection.execute("SELECT * FROM specimens WHERE case_id = ? ORDER BY label", (case_id,)).fetchall()
            )
            for specimen in specimens:
                blocks = self._rows(
                    connection.execute(
                        "SELECT * FROM blocks WHERE specimen_id = ? ORDER BY label", (specimen["id"],)
                    ).fetchall()
                )
                for block in blocks:
                    block["slides"] = self._rows(
                        connection.execute(
                            "SELECT * FROM slides WHERE block_id = ? ORDER BY label", (block["id"],)
                        ).fetchall()
                    )
                specimen["blocks"] = blocks
            result["specimens"] = specimens
            report = connection.execute("SELECT * FROM reports WHERE case_id = ?", (case_id,)).fetchone()
            result["report"] = None
            if report:
                report_data = dict(report)
                report_data["versions"] = self._rows(
                    connection.execute(
                        """SELECT rv.*, d.display_name AS author_name
                           FROM report_versions rv JOIN doctors d ON d.id = rv.author_id
                           WHERE rv.report_id = ? ORDER BY rv.version DESC""",
                        (report["id"],),
                    ).fetchall()
                )
                result["report"] = report_data
            return result

    def verify_audit_chain(self) -> bool:
        previous_hash = "0" * 64
        with self.connect() as connection:
            events = connection.execute("SELECT * FROM audit_events ORDER BY sequence").fetchall()
        for event in events:
            canonical = "|".join(
                [
                    previous_hash,
                    event["id"],
                    event["occurred_at"],
                    event["actor"],
                    event["action"],
                    event["entity_type"],
                    event["entity_id"],
                    event["details_json"],
                ]
            )
            if event["previous_hash"] != previous_hash:
                return False
            if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != event["event_hash"]:
                return False
            previous_hash = event["event_hash"]
        return True

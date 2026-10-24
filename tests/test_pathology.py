import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from allieos.pathology import PathologyError, PathologyStore
from allieos.pathology.server import _viewer_url, build_handler


class PathologyWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary_directory.name) / "pathology.db"
        self.store = PathologyStore(self.database)
        self.store.initialize()
        self.doctor_id = self.store.create_doctor(
            "Example Pathologist", external_id="DOC-DEMO-1", actor="test-admin"
        )
        self.patient_id = self.store.create_patient(
            "DEMO-MRN-1",
            "Example Patient",
            metadata={"source": "synthetic-test-data"},
            actor="test-clerk",
        )
        self.case_id = self.store.create_case(
            "DEMO-2026-001",
            self.patient_id,
            assigned_doctor_id=self.doctor_id,
            organ="Example organ",
            actor="test-clerk",
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def add_slide(self):
        specimen_id = self.store.add_specimen(
            self.case_id, "A", site="Example site", procedure="Example biopsy", actor="test-tech"
        )
        block_id = self.store.add_block(specimen_id, "A1", actor="test-tech")
        return self.store.add_slide(
            block_id,
            "A1-1",
            stain="H&E",
            study_instance_uid="1.2.826.0.1.3680043.10.1000.1",
            series_instance_uid="1.2.826.0.1.3680043.10.1000.2",
            sop_instance_uid="1.2.826.0.1.3680043.10.1000.3",
            actor="test-tech",
        )

    def test_end_to_end_case_slide_report_and_search(self):
        self.add_slide()
        report_id, draft_version = self.store.save_report_draft(
            self.case_id,
            self.doctor_id,
            "Synthetic test diagnosis",
            microscopic_description="Synthetic microscopy description.",
            actor="test-pathologist",
        )
        signed_version = self.store.sign_report(
            self.case_id, self.doctor_id, actor="test-pathologist"
        )

        self.assertTrue(report_id)
        self.assertEqual((draft_version, signed_version), (1, 2))
        results = self.store.search("Synthetic test diagnosis")
        self.assertEqual(results[0]["case_id"], self.case_id)
        case = self.store.get_case(self.case_id)
        patient = self.store.get_patient(self.patient_id)
        self.assertEqual(case["status"], "final")
        self.assertEqual(case["report"]["status"], "signed")
        self.assertEqual(len(case["report"]["versions"]), 2)
        self.assertEqual(case["specimens"][0]["blocks"][0]["slides"][0]["stain"], "H&E")
        self.assertEqual(patient["cases"][0]["slides"][0]["label"], "A1-1")
        self.assertEqual(patient["cases"][0]["current_diagnosis"], "Synthetic test diagnosis")
        self.assertTrue(self.store.verify_audit_chain())

    def test_signed_report_requires_explicit_amendment(self):
        self.store.save_report_draft(
            self.case_id, self.doctor_id, "Initial synthetic diagnosis", actor="test-pathologist"
        )
        self.store.sign_report(self.case_id, self.doctor_id, actor="test-pathologist")

        with self.assertRaisesRegex(PathologyError, "cannot be overwritten"):
            self.store.save_report_draft(
                self.case_id, self.doctor_id, "Replacement", actor="test-pathologist"
            )

        version = self.store.amend_report(
            self.case_id,
            self.doctor_id,
            "Amended synthetic diagnosis",
            "Synthetic correction reason",
            actor="test-pathologist",
        )
        self.assertEqual(version, 3)
        self.assertEqual(self.store.get_case(self.case_id)["status"], "amended")

        with self.assertRaisesRegex(PathologyError, "cannot be overwritten"):
            self.store.save_report_draft(
                self.case_id, self.doctor_id, "Replacement after amendment", actor="test-pathologist"
            )
        with self.assertRaisesRegex(PathologyError, "only a draft report"):
            self.store.sign_report(self.case_id, self.doctor_id, actor="test-pathologist")

    def test_report_versions_and_audit_events_are_immutable(self):
        self.store.save_report_draft(
            self.case_id, self.doctor_id, "Synthetic diagnosis", actor="test-pathologist"
        )
        with self.store.connect() as connection:
            version_id = connection.execute("SELECT id FROM report_versions").fetchone()["id"]
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE report_versions SET diagnosis = 'changed' WHERE id = ?", (version_id,)
                )
        with self.store.connect() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM audit_events")

    def test_slide_requires_archive_reference(self):
        specimen_id = self.store.add_specimen(self.case_id, "A", actor="test-tech")
        block_id = self.store.add_block(specimen_id, "A1", actor="test-tech")
        with self.assertRaisesRegex(PathologyError, "image_uri or sop_instance_uid"):
            self.store.add_slide(block_id, "A1-1", actor="test-tech")
        with self.assertRaisesRegex(PathologyError, "must use http or https"):
            self.store.add_slide(
                block_id, "A1-2", image_uri="javascript:alert(1)", actor="test-tech"
            )

    def test_search_supports_patient_metadata_and_doctor_filter(self):
        by_metadata = self.store.search("synthetic-test-data")
        by_doctor = self.store.search("", doctor_id=self.doctor_id)
        self.assertEqual(by_metadata[0]["case_id"], self.case_id)
        self.assertEqual(by_doctor[0]["case_id"], self.case_id)

    def test_viewer_template_uses_encoded_dicom_uids(self):
        slide = {
            "image_uri": None,
            "study_instance_uid": "1.2.3",
            "series_instance_uid": "4.5.6",
            "sop_instance_uid": "7.8.9",
        }
        url = _viewer_url(
            "https://viewer.invalid/?study={study_instance_uid}&series={series_instance_uid}&instance={sop_instance_uid}",
            slide,
        )
        self.assertEqual(
            url,
            "https://viewer.invalid/?study=1.2.3&series=4.5.6&instance=7.8.9",
        )

    def test_metadata_is_json_round_tripped(self):
        patient = self.store.get_patient(self.patient_id)
        self.assertEqual(patient["metadata"], {"source": "synthetic-test-data"})
        json.dumps(patient)


class PathologyHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        database = Path(self.temporary_directory.name) / "pathology.db"
        self.store = PathologyStore(database)
        self.store.initialize()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(self.store))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary_directory.cleanup()

    def request_json(self, path, *, body=None, content_type="application/json"):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(self.base_url + path, data=data)
        if data is not None:
            request.add_header("Content-Type", content_type)
            request.add_header("X-Remote-User", "http-test-user")
        with urlopen(request, timeout=2) as response:
            return response.status, dict(response.headers), json.load(response)

    def test_health_and_patient_creation(self):
        status, headers, health = self.request_json("/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(health, {"status": "ok", "audit_chain_valid": True})
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])

        status, _, created = self.request_json(
            "/api/patients",
            body={"mrn": "HTTP-DEMO-1", "display_name": "HTTP Example Patient"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(self.store.get_patient(created["id"])["mrn"], "HTTP-DEMO-1")

    def test_rejects_non_json_write(self):
        with self.assertRaises(HTTPError) as raised:
            self.request_json(
                "/api/patients",
                body={"mrn": "HTTP-DEMO-2", "display_name": "Example"},
                content_type="text/plain",
            )
        self.assertEqual(raised.exception.code, 400)
        self.assertEqual(json.load(raised.exception)["error"], "Content-Type must be application/json")


if __name__ == "__main__":
    unittest.main()

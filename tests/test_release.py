import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from allieos.profiles import Profile, discover_profiles
from allieos.release import ReleaseError, build_sboms, write_release_metadata


ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.profiles = discover_profiles(ROOT / "config" / "profiles").values()

    def test_sboms_are_deterministic_and_cover_every_package(self):
        spdx, cyclonedx = build_sboms(self.profiles, source_date_epoch=0)
        expected = {
            package
            for profile in discover_profiles(ROOT / "config" / "profiles").values()
            for package in profile.packages
        }
        self.assertEqual({item["name"] for item in spdx["packages"]}, expected)
        self.assertEqual({item["name"] for item in cyclonedx["components"]}, expected)
        self.assertEqual(spdx["creationInfo"]["created"], "1970-01-01T00:00:00Z")

    def test_shared_package_records_profile_membership(self):
        profiles = [
            Profile("lab", "Lab", "Lab profile", ("dcmtk",)),
            Profile("review", "Review", "Review profile", ("dcmtk",)),
        ]
        spdx, cyclonedx = build_sboms(profiles, source_date_epoch=0)
        self.assertIn("lab, review", spdx["packages"][0]["annotations"][0]["comment"])
        self.assertEqual(cyclonedx["components"][0]["properties"][0]["value"], "lab,review")

    def test_writer_checksums_sboms_and_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "allieos.iso"
            artifact.write_bytes(b"image")
            created = write_release_metadata(self.profiles, root / "release", [artifact], 0)

            self.assertEqual(len(created), 3)
            lines = (root / "release" / "SHA256SUMS").read_text().splitlines()
            entries = {line.split("  ", 1)[1]: line.split("  ", 1)[0] for line in lines}
            self.assertEqual(entries["allieos.iso"], hashlib.sha256(b"image").hexdigest())
            self.assertIn("allieos.spdx.json", entries)
            self.assertIn("allieos.cdx.json", entries)
            json.loads((root / "release" / "allieos.spdx.json").read_text())

    def test_missing_artifact_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release"
            with self.assertRaises(ReleaseError):
                write_release_metadata(self.profiles, output, [Path(directory) / "missing.iso"], 0)
            self.assertFalse(output.exists())

    def test_reserved_metadata_filename_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "allieos.spdx.json"
            artifact.write_text("do not overwrite")
            with self.assertRaises(ReleaseError):
                write_release_metadata(self.profiles, Path(directory), [artifact], 0)
            self.assertEqual(artifact.read_text(), "do not overwrite")


if __name__ == "__main__":
    unittest.main()

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from allieos.profiles import Profile, discover_profiles
from allieos.release import (
    PackageMetadata,
    ReleaseError,
    build_sboms,
    read_dpkg_status,
    write_release_metadata,
)


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
        components = {"Micro-Manager", "AllieOS Pathology Platform Integration"}
        self.assertEqual({item["name"] for item in spdx["packages"]}, expected | components)
        self.assertEqual({item["name"] for item in cyclonedx["components"]}, expected | components)
        self.assertEqual(spdx["creationInfo"]["created"], "1970-01-01T00:00:00Z")

    def test_micro_manager_revision_is_recorded(self):
        spdx, cyclonedx = build_sboms(self.profiles, source_date_epoch=0)
        spdx_component = next(item for item in spdx["packages"] if item["name"] == "Micro-Manager")
        cdx_component = next(item for item in cyclonedx["components"] if item["name"] == "Micro-Manager")
        revision = "bba80619603cf8974a0666c06c60ec68111d14b2"
        self.assertIn(revision, spdx_component["externalRefs"][0]["referenceLocator"])
        self.assertIn(revision, cdx_component["purl"])

    def test_pathology_platform_integration_is_recorded(self):
        spdx, cyclonedx = build_sboms(self.profiles, source_date_epoch=0)
        name = "AllieOS Pathology Platform Integration"
        self.assertEqual(next(item for item in spdx["packages"] if item["name"] == name)["versionInfo"], "0.1.0")
        self.assertEqual(next(item for item in cyclonedx["components"] if item["name"] == name)["purl"], "pkg:generic/allieos-pathology-platform@0.1.0")

    def test_operating_system_release_name_and_codename_are_recorded(self):
        spdx, cyclonedx = build_sboms(self.profiles, source_date_epoch=0)
        operating_system = cyclonedx["metadata"]["component"]

        self.assertEqual(operating_system["name"], "AllieOS")
        self.assertEqual(operating_system["version"], "0.1.0")
        self.assertEqual(
            spdx["name"],
            "AllieOS-0.1.0-Rainbow-Dress-profile-components",
        )
        self.assertEqual(
            operating_system["properties"],
            [{"name": "allieos:codename", "value": "Rainbow Dress"}],
        )

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

    def test_dpkg_status_enriches_package_versions_and_architectures(self):
        profiles = [Profile("lab", "Lab", "Lab profile", ("dcmtk",))]
        inventory = {"dcmtk": PackageMetadata("3.6.7-9ubuntu2", "amd64")}
        spdx, cyclonedx = build_sboms(profiles, 0, inventory)

        self.assertEqual(spdx["packages"][0]["versionInfo"], "3.6.7-9ubuntu2")
        self.assertIn("@3.6.7-9ubuntu2?arch=amd64", spdx["packages"][0]["externalRefs"][0]["referenceLocator"])
        self.assertEqual(cyclonedx["components"][0]["version"], "3.6.7-9ubuntu2")
        self.assertIn(
            {"name": "allieos:architecture", "value": "amd64"},
            cyclonedx["components"][0]["properties"],
        )

    def test_dpkg_status_parser_only_returns_installed_packages(self):
        status = """Package: dcmtk
Status: install ok installed
Architecture: amd64
Version: 3.6.7-9ubuntu2
Description: DICOM toolkit
 continued description

Package: removed-package
Status: deinstall ok config-files
Architecture: amd64
Version: 1.0
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status"
            path.write_text(status, encoding="utf-8")
            self.assertEqual(
                read_dpkg_status(path),
                {"dcmtk": PackageMetadata("3.6.7-9ubuntu2", "amd64")},
            )

    def test_inventory_must_contain_every_declared_package(self):
        profiles = [Profile("lab", "Lab", "Lab profile", ("dcmtk", "orthanc"))]
        with self.assertRaisesRegex(ReleaseError, "orthanc"):
            build_sboms(
                profiles,
                0,
                {"dcmtk": PackageMetadata("3.6.7-9ubuntu2", "amd64")},
            )

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

from pathlib import Path
import tempfile
import unittest

from allieos.profiles import (
    Profile,
    ProfileError,
    discover_profiles,
    load_profile,
    resolve_components,
    resolve_packages,
)


ROOT = Path(__file__).resolve().parents[1]


class ProfileTests(unittest.TestCase):
    def test_repository_profiles_are_valid(self):
        profiles = discover_profiles(ROOT / "config" / "profiles")
        self.assertEqual(
            set(profiles),
            {"clinician", "engineer", "medical-student", "pathology-lab", "scientist", "technician"},
        )

    def test_packages_are_sorted_and_deduplicated(self):
        first = Profile("a", "A", "A profile", ("git", "python3", "git"))
        second = Profile("b", "B", "B profile", ("python3", "cmake"))
        self.assertEqual(resolve_packages([first, second]), ["cmake", "git", "python3"])

    def test_components_are_sorted_and_deduplicated(self):
        first = Profile("a", "A", "A profile", ("git",), ("micro-manager",))
        second = Profile("b", "B", "B profile", ("git",), ("micro-manager", "other"))
        self.assertEqual(resolve_components([first, second]), ["micro-manager", "other"])

    def test_pathology_profile_includes_complete_platform(self):
        profile = load_profile(ROOT / "config" / "profiles" / "pathology-lab.toml")
        self.assertIn("micro-manager", profile.components)
        self.assertIn("pathology-platform", profile.components)
        self.assertTrue(
            {"orthanc", "orthanc-dicomweb", "orthanc-gdcm", "orthanc-wsi"}.issubset(profile.packages)
        )

    def test_filename_and_id_must_match(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrong.toml"
            path.write_text('id="different"\nname="Name"\ndescription="Description"\npackages=["git"]\n')
            with self.assertRaises(ProfileError):
                load_profile(path)


if __name__ == "__main__":
    unittest.main()

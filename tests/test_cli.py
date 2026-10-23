from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from allieos.cli import main


PROFILE_DIR = Path(__file__).resolve().parents[1] / "config" / "profiles"
ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--profile-dir", str(PROFILE_DIR), *args])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_list(self):
        code, output, _ = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("pathology-lab", output)
        self.assertIn("scientist", output)

    def test_packages_lists_every_profile_package_once(self):
        code, output, error = self.run_cli("packages")
        self.assertEqual((code, error), (0, ""))
        packages = output.splitlines()
        self.assertEqual(packages, sorted(set(packages)))
        self.assertIn("dicomscope", packages)
        self.assertIn("jupyter-notebook", packages)
        self.assertIn("kicad", packages)
        self.assertIn("openslide-tools", packages)
        self.assertIn("wireshark", packages)

    def test_combined_dry_run_is_deduplicated(self):
        code, output, _ = self.run_cli("apply", "clinician", "pathology-lab", "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(output.split().count("dcmtk"), 1)
        self.assertTrue(output.startswith("apt-get install --yes"))
        self.assertEqual(output.count("install-micromanager.sh"), 1)

    def test_show_lists_external_components(self):
        code, output, error = self.run_cli("show", "pathology-lab")
        self.assertEqual((code, error), (0, ""))
        self.assertIn("External components:", output)
        self.assertIn("micro-manager", output)

    def test_live_image_preinstalls_micro_manager(self):
        recipe = (ROOT / "scripts" / "build-image.sh").read_text(encoding="utf-8")
        installer = (ROOT / "scripts" / "install-micromanager.sh").read_text(encoding="utf-8")
        self.assertIn("0200-allieos-micromanager.hook.chroot", recipe)
        self.assertIn("/usr/libexec/allieos/install-micromanager.sh", recipe)
        self.assertIn("allieos-profiles.list.chroot", recipe)
        self.assertIn("org.micro-manager.MicroManager.desktop", installer)

    def test_unknown_profile(self):
        code, _, error = self.run_cli("show", "unknown")
        self.assertEqual(code, 2)
        self.assertIn("unknown profile", error)

    def test_release_metadata_command(self):
        with tempfile.TemporaryDirectory() as directory:
            code, output, error = self.run_cli(
                "release-metadata", "--output-dir", directory, "--source-date-epoch", "0"
            )
            self.assertEqual((code, error), (0, ""))
            self.assertIn("allieos.spdx.json", output)
            self.assertTrue((Path(directory) / "SHA256SUMS").is_file())


if __name__ == "__main__":
    unittest.main()

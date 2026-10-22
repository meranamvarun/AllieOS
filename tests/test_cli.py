from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import unittest

from allieos.cli import main


PROFILE_DIR = Path(__file__).resolve().parents[1] / "config" / "profiles"


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

    def test_combined_dry_run_is_deduplicated(self):
        code, output, _ = self.run_cli("apply", "clinician", "pathology-lab", "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(output.split().count("dcmtk"), 1)
        self.assertTrue(output.startswith("apt-get install --yes"))

    def test_unknown_profile(self):
        code, _, error = self.run_cli("show", "unknown")
        self.assertEqual(code, 2)
        self.assertIn("unknown profile", error)


if __name__ == "__main__":
    unittest.main()

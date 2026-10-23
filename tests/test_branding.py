from pathlib import Path
import unittest
import xml.etree.ElementTree as ElementTree


ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "branding" / "plymouth" / "allieos"


class BrandingTests(unittest.TestCase):
    def test_plymouth_theme_references_existing_sources(self):
        descriptor = (THEME / "allieos.plymouth").read_text(encoding="utf-8")
        script = (THEME / "allieos.script").read_text(encoding="utf-8")

        self.assertIn("ModuleName=script", descriptor)
        self.assertIn("Plymouth.SetRefreshFunction", script)
        for asset in ("field", "cell", "nucleus", "focus-ring", "scan-line"):
            source = THEME / f"{asset}.svg"
            self.assertTrue(source.is_file())
            ElementTree.parse(source)
            self.assertIn(f'Image("{asset}.png")', script)

    def test_live_build_installs_and_selects_theme(self):
        build_script = (ROOT / "scripts" / "build-image.sh").read_text(encoding="utf-8")
        packages = (ROOT / "config" / "live" / "base-packages.list.chroot").read_text(
            encoding="utf-8"
        ).splitlines()

        self.assertIn("plymouth-themes", packages)
        self.assertIn("librsvg2-bin", packages)
        self.assertIn('branding/plymouth/allieos/', build_script)
        self.assertIn("rsvg-convert", build_script)
        self.assertIn("update-initramfs -u", build_script)


if __name__ == "__main__":
    unittest.main()

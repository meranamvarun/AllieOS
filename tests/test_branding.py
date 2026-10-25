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
        self.assertIn("RAINBOW DRESS", script)
        self.assertIn(
            "Rainbow Dress",
            (ROOT / "branding" / "allieos-wallpaper.svg").read_text(encoding="utf-8"),
        )
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

    def test_live_image_identifies_itself_as_allieos_rainbow_dress(self):
        build_script = (ROOT / "scripts" / "build-image.sh").read_text(encoding="utf-8")

        self.assertIn('PRETTY_NAME="AllieOS 0.1.0 (Rainbow Dress)"', build_script)
        self.assertIn('VERSION_CODENAME=rainbow-dress', build_script)
        self.assertIn('ID=allieos', build_script)
        self.assertIn('DISTRIB_ID=AllieOS', build_script)
        self.assertIn('DISTRIB_CODENAME=rainbow-dress', build_script)
        self.assertIn("/etc/issue.net", build_script)
        self.assertIn("/etc/update-motd.d/00-allieos", build_script)
        self.assertIn('GRUB_DISTRIBUTOR="AllieOS"', build_script)
        self.assertNotIn("PRETTY_NAME=Ubuntu", build_script)
        os_release = build_script.split("cat > /etc/os-release <<'RELEASE'", 1)[1].split(
            "\nRELEASE", 1
        )[0]
        self.assertNotIn("ubuntu", os_release.lower())


if __name__ == "__main__":
    unittest.main()

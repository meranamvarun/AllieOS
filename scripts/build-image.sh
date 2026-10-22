#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${ROOT_DIR}/build/live"

if [[ "$(uname -s)" != "Linux" ]] || ! grep -q '^ID=ubuntu$' /etc/os-release; then
  echo "Builds require an Ubuntu 24.04 host or VM." >&2
  exit 2
fi
if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo ./scripts/build-image.sh" >&2
  exit 2
fi
for command in lb rsync; do
  command -v "${command}" >/dev/null || { echo "Missing ${command}; run: sudo apt install live-build rsync" >&2; exit 2; }
done

mkdir -p "${BUILD_DIR}"
cd "${BUILD_DIR}"
lb clean --purge 2>/dev/null || true
lb config noauto \
  --mode ubuntu \
  --architectures amd64 \
  --distribution noble \
  --archive-areas "main restricted universe multiverse" \
  --binary-images iso-hybrid \
  --debian-installer none \
  --image-name allieos-0.1.0-amd64 \
  --iso-application "AllieOS Live" \
  --iso-publisher "AllieOS contributors" \
  --iso-volume "ALLIEOS_0_1" \
  --bootappend-live "boot=live components username=allie hostname=allieos"

mkdir -p config/package-lists config/includes.chroot/opt/allieos \
  config/includes.chroot/usr/local/bin config/includes.chroot/usr/share/allieos/profiles \
  config/includes.chroot/usr/share/backgrounds/allieos config/includes.chroot/etc/apt/apt.conf.d
cp "${ROOT_DIR}/config/live/base-packages.list.chroot" config/package-lists/allieos.list.chroot
cp "${ROOT_DIR}/config/live/99-allieos-security" config/includes.chroot/etc/apt/apt.conf.d/
cp "${ROOT_DIR}/branding/allieos-wallpaper.svg" config/includes.chroot/usr/share/backgrounds/allieos/
rsync -a "${ROOT_DIR}/allieos/" config/includes.chroot/opt/allieos/allieos/
cp "${ROOT_DIR}/config/profiles/"*.toml config/includes.chroot/usr/share/allieos/profiles/

cat > config/includes.chroot/usr/local/bin/alliectl <<'WRAPPER'
#!/usr/bin/env python3
import sys
sys.path.insert(0, "/opt/allieos")
from allieos.cli import main
raise SystemExit(main())
WRAPPER
chmod 0755 config/includes.chroot/usr/local/bin/alliectl

mkdir -p config/hooks/live
cat > config/hooks/live/0100-allieos-branding.hook.chroot <<'HOOK'
#!/bin/sh
set -eu
printf '\nVARIANT="AllieOS"\nVARIANT_ID=allieos\n' >> /etc/os-release
update-alternatives --install /usr/share/backgrounds/warty-final-ubuntu.png desktop-background /usr/share/backgrounds/allieos/allieos-wallpaper.svg 50 || true
HOOK
chmod 0755 config/hooks/live/0100-allieos-branding.hook.chroot

lb build
echo "Image build complete. Artifacts are in ${BUILD_DIR}."

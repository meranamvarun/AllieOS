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
  config/includes.chroot/opt/allieos/docs/third-party \
  config/includes.chroot/usr/local/bin config/includes.chroot/usr/libexec/allieos \
  config/includes.chroot/usr/share/allieos/profiles \
  config/includes.chroot/usr/share/backgrounds/allieos \
  config/includes.chroot/usr/share/plymouth/themes/allieos \
  config/includes.chroot/etc/apt/apt.conf.d
cp "${ROOT_DIR}/config/live/base-packages.list.chroot" config/package-lists/allieos.list.chroot
(cd "${ROOT_DIR}" && python3 -m allieos.cli \
  --profile-dir "${ROOT_DIR}/config/profiles" packages) \
  > config/package-lists/allieos-profiles.list.chroot
cp "${ROOT_DIR}/config/live/99-allieos-security" config/includes.chroot/etc/apt/apt.conf.d/
cp "${ROOT_DIR}/branding/allieos-wallpaper.svg" config/includes.chroot/usr/share/backgrounds/allieos/
cp "${ROOT_DIR}/branding/plymouth/allieos/"* config/includes.chroot/usr/share/plymouth/themes/allieos/
rsync -a "${ROOT_DIR}/allieos/" config/includes.chroot/opt/allieos/allieos/
cp "${ROOT_DIR}/docs/PATHOLOGY_SYSTEM.md" config/includes.chroot/opt/allieos/docs/
cp "${ROOT_DIR}/docs/third-party/pathology-platform.md" \
  config/includes.chroot/opt/allieos/docs/third-party/
cp "${ROOT_DIR}/config/profiles/"*.toml config/includes.chroot/usr/share/allieos/profiles/
install -m 0755 "${ROOT_DIR}/scripts/install-micromanager.sh" \
  config/includes.chroot/usr/libexec/allieos/install-micromanager.sh
install -m 0755 "${ROOT_DIR}/scripts/install-pathology-platform.sh" \
  config/includes.chroot/usr/libexec/allieos/install-pathology-platform.sh

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

THEME_DIR=/usr/share/plymouth/themes/allieos
for asset in field cell nucleus focus-ring scan-line; do
  rsvg-convert "${THEME_DIR}/${asset}.svg" -o "${THEME_DIR}/${asset}.png"
done
update-alternatives --install /usr/share/plymouth/themes/default.plymouth default.plymouth "${THEME_DIR}/allieos.plymouth" 200
update-alternatives --set default.plymouth "${THEME_DIR}/allieos.plymouth"
update-initramfs -u
HOOK
chmod 0755 config/hooks/live/0100-allieos-branding.hook.chroot

cat > config/hooks/live/0200-allieos-micromanager.hook.chroot <<'HOOK'
#!/bin/sh
set -eu
/usr/libexec/allieos/install-micromanager.sh
test -x /opt/micro-manager/2.0.3-bba80619603c/bin/micromanager
test -L /usr/local/bin/micromanager
HOOK
chmod 0755 config/hooks/live/0200-allieos-micromanager.hook.chroot

cat > config/hooks/live/0300-allieos-pathology-platform.hook.chroot <<'HOOK'
#!/bin/sh
set -eu
/usr/libexec/allieos/install-pathology-platform.sh
test -x /usr/local/bin/allie-pathology
test -x /usr/local/bin/allie-pathology-launch
test -f /usr/lib/systemd/user/allie-pathology.service
test -f /usr/local/share/applications/org.allieos.Pathology.desktop
test -f /etc/orthanc/zz-allieos-local.json
HOOK
chmod 0755 config/hooks/live/0300-allieos-pathology-platform.hook.chroot

lb build

mapfile -t IMAGE_ARTIFACTS < <(find "${BUILD_DIR}" -maxdepth 1 -type f \( -name '*.iso' -o -name '*.img' \) -print | sort)
if [[ "${#IMAGE_ARTIFACTS[@]}" -eq 0 ]]; then
  echo "Image build completed but no ISO or IMG artifact was found." >&2
  exit 2
fi

METADATA_ARGS=(--profile-dir "${ROOT_DIR}/config/profiles" release-metadata --output-dir "${ROOT_DIR}/build/release")
for artifact in "${IMAGE_ARTIFACTS[@]}"; do
  METADATA_ARGS+=(--artifact "${artifact}")
done
(cd "${ROOT_DIR}" && python3 -m allieos.cli "${METADATA_ARGS[@]}")

echo "Image build complete. Images are in ${BUILD_DIR}; release metadata is in ${ROOT_DIR}/build/release."

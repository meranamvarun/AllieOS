#!/usr/bin/env bash
set -euo pipefail

# Integrate the AllieOS workflow service with the Ubuntu-packaged Orthanc stack.
# The packages themselves are declared in the pathology-lab profile so they are
# downloaded into the ISO by live-build and remain tracked by the release SBOM.

if [[ "$(uname -s)" != "Linux" ]] || ! grep -q '^ID=ubuntu$' /etc/os-release; then
  echo "The pathology platform installer requires Ubuntu." >&2
  exit 2
fi
if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root through alliectl or sudo." >&2
  exit 2
fi

for package in orthanc orthanc-dicomweb orthanc-gdcm orthanc-wsi; do
  dpkg-query -W -f='${Status}' "${package}" 2>/dev/null | grep -q 'install ok installed' || {
    echo "Required package is not installed: ${package}" >&2
    exit 2
  }
done

install -d -m 0755 /usr/local/bin /usr/local/share/applications /usr/lib/systemd/user /etc/orthanc

cat > /usr/local/bin/allie-pathology <<'WRAPPER'
#!/usr/bin/env python3
import sys
sys.path.insert(0, "/opt/allieos")
from allieos.pathology.server import main
raise SystemExit(main())
WRAPPER
chmod 0755 /usr/local/bin/allie-pathology

cat > /usr/local/bin/allie-pathology-launch <<'LAUNCHER'
#!/bin/sh
set -eu
systemctl --user start allie-pathology.service
attempt=0
while ! curl --fail --silent http://127.0.0.1:8090/healthz >/dev/null; do
  attempt=$((attempt + 1))
  if [ "${attempt}" -ge 50 ]; then
    echo "AllieOS Pathology did not become ready." >&2
    exit 2
  fi
  sleep 0.1
done
exec xdg-open http://127.0.0.1:8090/
LAUNCHER
chmod 0755 /usr/local/bin/allie-pathology-launch

cat > /usr/lib/systemd/user/allie-pathology.service <<'UNIT'
[Unit]
Description=AllieOS local pathology workflow
Documentation=file:///opt/allieos/docs/PATHOLOGY_SYSTEM.md
After=default.target

[Service]
Type=simple
ExecStartPre=/usr/bin/mkdir -p %h/.local/share/allieos
ExecStart=/usr/local/bin/allie-pathology --database=%h/.local/share/allieos/pathology.db --port=8090
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=%h/.local/share/allieos

[Install]
WantedBy=default.target
UNIT
chmod 0644 /usr/lib/systemd/user/allie-pathology.service

cat > /usr/local/share/applications/org.allieos.Pathology.desktop <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=AllieOS Pathology
Comment=Manage pathology cases, slides, and report history
Exec=/usr/local/bin/allie-pathology-launch
Icon=applications-science
Terminal=false
Categories=Science;MedicalSoftware;
StartupNotify=true
DESKTOP
chmod 0644 /usr/local/share/applications/org.allieos.Pathology.desktop

# Orthanc's Debian/Ubuntu service reads the JSON fragments in /etc/orthanc.
# Keep the bundled archive on loopback; a site must explicitly configure an
# authenticated TLS boundary before permitting remote access.
cat > /etc/orthanc/zz-allieos-local.json <<'ORTHANC'
{
  "Name": "AllieOS Local WSI Archive",
  "RemoteAccessAllowed": false,
  "AuthenticationEnabled": false
}
ORTHANC
chmod 0640 /etc/orthanc/zz-allieos-local.json
chown root:orthanc /etc/orthanc/zz-allieos-local.json

systemctl enable orthanc.service >/dev/null 2>&1 || true
echo "Installed the bundled AllieOS pathology workflow and local WSI archive integration."

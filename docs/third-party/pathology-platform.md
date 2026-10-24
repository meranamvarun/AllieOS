# Bundled pathology platform provenance and lifecycle

## Components

AllieOS 0.1 targets Ubuntu 24.04 LTS Noble and installs these packages from the
Ubuntu `universe` repository through the `pathology-lab` profile:

| Package | Noble version reviewed | Purpose | Upstream license family |
| --- | --- | --- | --- |
| `orthanc` | `1.12.2+dfsg-1build4` | Local DICOM archive and REST service | GPL-3.0-or-later |
| `orthanc-dicomweb` | `1.16+dfsg-1build2` | WADO-RS, QIDO-RS, and STOW-RS | GPL/AGPL-compatible Orthanc plugin |
| `orthanc-gdcm` | `1.6+dfsg-1build2` | GDCM transcoding, including JPEG2000 workflows | GPL/AGPL-compatible Orthanc plugin |
| `orthanc-wsi` | `2.0+dfsg-2build5` | Whole-slide conversion and web viewing | AGPL-3.0-or-later |

The authoritative license for a built ISO is the copyright metadata shipped in
its exact `.deb` packages. Versions above are review anchors, not replacements
for the completed-image inventory. Ubuntu may publish security or stable-release
updates without changing the AllieOS source manifest.

The AllieOS workflow and integration code is GPL-3.0-only and is copied from the
same source tree used to build the ISO. It uses Python's standard library and
communicates with Orthanc over HTTP/DICOM boundaries rather than linking against
the Orthanc plugin SDK.

## Inclusion and isolation decision

The ISO is the primary AllieOS product, so all four archive packages and the
workflow service are included rather than downloaded after installation. The
archive and workflow bind to loopback by default. No cloud account, telemetry,
public listener, or default remote credential is configured.

The workflow runs as a per-user systemd service with filesystem restrictions.
Orthanc runs as its distribution service and owns image storage separately from
the report database. Sites enabling remote use must add an authenticated TLS
proxy, access control, durable encrypted storage, backup and recovery, and local
clinical validation.

## Update ownership

AllieOS maintainers own:

- monitoring Ubuntu Noble updates and CVEs for all four packages;
- checking plugin compatibility before accepting an ISO update;
- generating and reviewing SPDX/CycloneDX output from the completed image;
- retaining or making available corresponding source required by GPL/AGPL;
- regression testing DICOM ingest, WSI rendering, and workflow deep links.

Because these packages are in Ubuntu `universe`, the project must not imply the
same security-maintenance commitment as packages in Ubuntu `main`.

## Removal and rollback

On an installed AllieOS system, stop the local workflow and remove its desktop
integration before removing packages:

```bash
systemctl --user disable --now allie-pathology.service
sudo systemctl disable --now orthanc.service
sudo apt remove orthanc-wsi orthanc-gdcm orthanc-dicomweb orthanc
```

The workflow database remains at
`~/.local/share/allieos/pathology.db`; Orthanc data normally remains below
`/var/lib/orthanc`. Neither is deleted automatically. Data destruction requires
an institution-approved retention and disposal process.

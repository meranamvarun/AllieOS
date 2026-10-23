# AllieOS

AllieOS is an Ubuntu-based Linux environment for clinicians, pathology and laboratory staff, medical students, scientists, engineers, and biomedical/IT technicians. It combines a conservative Ubuntu 24.04 LTS base with a preinstalled pathology and laboratory toolkit organized through composable professional profiles.

> **Clinical safety:** AllieOS is not a medical device and is not validated for diagnosis. Applications must be independently validated before clinical use. Never use real patient data in development or demonstrations.

## What works today

- Six validated role manifests with deterministic package resolution.
- All packages from all six profiles preinstalled in the live ISO.
- Micro-Manager 2.0.3 preinstalled in the live ISO from pinned upstream source.
- An H&E-inspired animated microscopy boot splash.
- `alliectl` to list, inspect, and apply multiple roles.
- An Ubuntu `live-build` recipe for an amd64 live ISO.
- Automatic security-update defaults and AppArmor in the base image.
- SPDX and CycloneDX package-manifest SBOMs with SHA-256 release checksums.
- Unit tests, package-availability validation, and CI.

This is an early developer release, not yet a production clinical workstation. The current ISO is a **live evaluation image**, not a supported installer.

## Try the role manager

Python 3.11 or newer is required.

```bash
python3 -m allieos.cli list
python3 -m allieos.cli show pathology-lab
python3 -m allieos.cli apply pathology-lab scientist --dry-run
```

On an installed Ubuntu 24.04 system, install the project and apply profiles with root privileges:

```bash
python3 -m pip install .
sudo alliectl apply pathology-lab scientist
```

The live ISO contains every profile package and Micro-Manager preinstalled. The profiles remain useful for inspecting the intended tool groupings and for applying the same setup to a regular Ubuntu installation. On regular Ubuntu, the pathology/lab profile builds Micro-Manager from the same pinned upstream source because no Linux binary is published. Microscope and camera drivers remain hardware-specific and must be installed and validated separately. See [Micro-Manager provenance and lifecycle](docs/third-party/micro-manager.md).

## Build the live image

Use a disposable Ubuntu 24.04 amd64 VM with at least 60 GB free space. Building downloads every profile package, compiles Micro-Manager inside the image, and runs chroot operations.

```bash
sudo apt update
sudo apt install live-build rsync
sudo bash ./scripts/build-image.sh
```

The image is written below `build/live/`. Boot it in a VM before trying hardware. Secure Boot signing and a graphical installer are planned but not implemented.
The build also writes `build/release/allieos.spdx.json`, `allieos.cdx.json`, and `SHA256SUMS`.

To generate the metadata separately, optionally including an existing image:

```bash
SOURCE_DATE_EPOCH=0 python3 -m allieos.cli release-metadata \
  --output-dir build/release --artifact build/live/allieos.iso
```

The SBOMs describe packages requested by AllieOS role manifests and the profiles that requested them. They do not replace an installed-package inventory or vulnerability scan of the completed image.

## Develop

```bash
python3 -m unittest discover -s tests -v
python3 -m allieos.cli list
bash ./scripts/validate-packages.sh   # on Ubuntu after apt update
```

See [the product and delivery plan](docs/PROJECT_PLAN.md), [architecture decisions](docs/ARCHITECTURE.md), and [security policy](SECURITY.md).

## License

GPL-3.0-only. See [LICENSE](LICENSE).

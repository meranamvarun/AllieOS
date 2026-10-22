# AllieOS

AllieOS is an Ubuntu-based Linux environment for clinicians, pathology and laboratory staff, medical students, scientists, engineers, and biomedical/IT technicians. It combines a conservative Ubuntu 24.04 LTS base with optional, composable professional profiles.

> **Clinical safety:** AllieOS is not a medical device and is not validated for diagnosis. Applications must be independently validated before clinical use. Never use real patient data in development or demonstrations.

## What works today

- Six validated role manifests with deterministic package resolution.
- `alliectl` to list, inspect, and apply multiple roles.
- An Ubuntu `live-build` recipe for an amd64 live ISO.
- Automatic security-update defaults and AppArmor in the base image.
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

## Build the live image

Use a disposable Ubuntu 24.04 amd64 VM with at least 30 GB free space. Building downloads several gigabytes and runs chroot operations.

```bash
sudo apt update
sudo apt install live-build rsync
sudo bash ./scripts/build-image.sh
```

The image is written below `build/live/`. Boot it in a VM before trying hardware. Secure Boot signing and a graphical installer are planned but not implemented.

## Develop

```bash
python3 -m unittest discover -s tests -v
python3 -m allieos.cli list
bash ./scripts/validate-packages.sh   # on Ubuntu after apt update
```

See [the product and delivery plan](docs/PROJECT_PLAN.md), [architecture decisions](docs/ARCHITECTURE.md), and [security policy](SECURITY.md).

## License

GPL-3.0-only. See [LICENSE](LICENSE).

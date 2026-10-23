# CLAUDE.md

## Project purpose

AllieOS is an Ubuntu 24.04 LTS-based pathology and laboratory workstation. Treat the product direction as a complete, prebundled specialist distribution—similar in packaging philosophy to Kali Linux, but for pathology, microscopy, laboratory work, biomedical engineering, and related education and research workflows.

AllieOS is not a medical device and is not validated for diagnosis. Do not claim that bundled software is suitable for regulated clinical use. Never add real patient data to source, tests, examples, logs, or images.

## Current product model

- The live ISO contains the union of packages from all six profiles.
- Profiles organize tools by workflow and reproduce the same setup on an existing Ubuntu installation; they are not download gates for the ISO.
- The six profiles are `clinician`, `pathology-lab`, `medical-student`, `scientist`, `engineer`, and `technician`.
- `alliectl` lists, inspects, combines, and applies profiles.
- Micro-Manager 2.0.3 is built from pinned source inside the live-image chroot and is preinstalled in the ISO.
- Micro-Manager remains an external component of the `pathology-lab` profile so that `alliectl apply pathology-lab` can install it on regular Ubuntu systems.
- Release metadata includes SPDX and CycloneDX SBOMs plus SHA-256 checksums.

## Important paths

- `config/profiles/*.toml`: profile definitions and Ubuntu package lists.
- `config/live/`: base live-image packages and security configuration.
- `allieos/profiles.py`: profile loading, validation, and deterministic resolution.
- `allieos/cli.py`: `alliectl` commands and registered external-component installers.
- `allieos/release.py`: SPDX, CycloneDX, and checksum generation.
- `scripts/build-image.sh`: Ubuntu live ISO recipe. It generates a package list containing every profile package and runs the Micro-Manager build hook.
- `scripts/install-micromanager.sh`: pinned, idempotent Micro-Manager source installer and desktop integration.
- `docs/third-party/micro-manager.md`: provenance, licensing, sandbox decision, update ownership, and removal procedure.
- `tests/`: unit and CLI coverage.

## Development commands

Run from the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 -m allieos.cli list
python3 -m allieos.cli packages
python3 -m allieos.cli show pathology-lab
python3 -m allieos.cli apply pathology-lab scientist --dry-run
```

On Ubuntu 24.04 after `apt update`, validate every declared package:

```bash
bash ./scripts/validate-packages.sh
```

Build the ISO only on a disposable Ubuntu 24.04 amd64 machine or VM with root access and at least 60 GB free:

```bash
sudo apt update
sudo apt install live-build rsync
sudo bash ./scripts/build-image.sh
```

The image is written below `build/live/`; release metadata is written below `build/release/`.

## Change requirements

- Keep package lists deterministic, duplicate-free, and available in the configured Ubuntu Noble repositories.
- When adding a package to a profile, remember that it will also be installed in the ISO.
- Do not add arbitrary executable hooks to profile TOML. External components require a named, reviewed installer registered in `alliectl`.
- Pin third-party sources and verify them by checksum, signature, immutable revision, or an appropriate combination.
- Record third-party provenance, license information, update ownership, sandbox decisions, and removal instructions.
- Add external components to both SPDX and CycloneDX output.
- Preserve the Micro-Manager desktop launcher and command-line entry point.
- Keep hardware-specific microscope and camera drivers separate unless their redistribution terms and hardware support have been reviewed.
- Update tests and documentation with behavior changes.

## Verification expectations

Run the unit suite and `git diff --check` for every code change. Changes to the live-image recipe or source installer also require Ubuntu CI validation. A successful Windows unit run does not prove that the Linux ISO or Micro-Manager source build succeeds.

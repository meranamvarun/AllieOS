"""Command line interface for applying AllieOS roles."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Sequence

from . import __codename__, __version__
from .profiles import (
    ProfileError,
    default_profile_dir,
    discover_profiles,
    resolve_components,
    resolve_packages,
)
from .release import ReleaseError, read_dpkg_status, write_release_metadata


STATE_FILE = Path("/var/lib/allieos/state.json")
COMPONENT_INSTALLERS = {
    "micro-manager": "install-micromanager.sh",
    "pathology-platform": "install-pathology-platform.sh",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alliectl", description="Manage AllieOS role profiles")
    parser.add_argument("--profile-dir", type=Path, default=default_profile_dir())
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__} ({__codename__})"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="list available profiles")
    show = subparsers.add_parser("show", help="show a profile and its packages")
    show.add_argument("profile")
    subparsers.add_parser("packages", help="list the packages required by all profiles")
    apply = subparsers.add_parser("apply", help="install one or more profiles")
    apply.add_argument("profiles", nargs="+")
    apply.add_argument("--dry-run", action="store_true", help="print the apt command without changing the system")
    subparsers.add_parser("status", help="show previously applied profiles")
    release = subparsers.add_parser("release-metadata", help="write SBOMs and SHA-256 checksums")
    release.add_argument("--output-dir", type=Path, default=Path("release"))
    release.add_argument("--artifact", action="append", type=Path, default=[], help="artifact to include in SHA256SUMS")
    release.add_argument("--source-date-epoch", type=int, help="fixed timestamp for reproducible output")
    release.add_argument(
        "--dpkg-status",
        type=Path,
        help="dpkg status file from the completed image; adds installed versions and architectures",
    )
    return parser


def _select(names: Sequence[str], available: dict):
    missing = sorted(set(names) - available.keys())
    if missing:
        raise ProfileError(f"unknown profile(s): {', '.join(missing)}")
    return [available[name] for name in names]


def _write_state(names: Sequence[str], packages: Sequence[str], components: Sequence[str]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": 2,
        "profiles": sorted(set(names)),
        "packages": list(packages),
        "components": list(components),
    }
    STATE_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _component_installer(component: str) -> Path:
    try:
        filename = COMPONENT_INSTALLERS[component]
    except KeyError as error:
        raise ProfileError(f"no installer is registered for component: {component}") from error
    system_path = Path("/usr/libexec/allieos") / filename
    if system_path.is_file():
        return system_path
    installed_path = shutil.which(filename)
    if installed_path:
        return Path(installed_path)
    source_path = Path(__file__).resolve().parent.parent / "scripts" / filename
    if source_path.is_file():
        return source_path
    raise ProfileError(f"component installer is missing: {filename}")


def _apply(
    names: Sequence[str], packages: Sequence[str], components: Sequence[str], dry_run: bool
) -> int:
    command = ["apt-get", "install", "--yes", *packages]
    if dry_run:
        print(" ".join(command))
        for component in components:
            print(f"bash {_component_installer(component)}")
        return 0
    if platform.system() != "Linux" or not Path("/etc/os-release").exists():
        raise ProfileError("profiles can only be applied on AllieOS or a compatible Linux system")
    os_release = Path("/etc/os-release").read_text(encoding="utf-8")
    release_fields = dict(
        line.split("=", 1) for line in os_release.splitlines() if "=" in line
    )
    system_id = release_fields.get("ID", "").strip('"')
    compatible_ids = release_fields.get("ID_LIKE", "").strip('"').split()
    if system_id not in {"allieos", "ubuntu"} and "ubuntu" not in compatible_ids:
        raise ProfileError("profiles require AllieOS or an Ubuntu-compatible base")
    if os.geteuid() != 0:
        raise ProfileError("apply must be run as root (try: sudo alliectl apply ...)")
    subprocess.run(["apt-get", "update"], check=True)
    subprocess.run(command, check=True)
    for component in components:
        subprocess.run(["bash", str(_component_installer(component))], check=True)
    _write_state(names, packages, components)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        profiles = discover_profiles(args.profile_dir)
        if args.command == "list":
            for profile in profiles.values():
                print(f"{profile.id:<20} {profile.name} — {profile.description}")
            return 0
        if args.command == "show":
            profile = _select([args.profile], profiles)[0]
            print(f"{profile.name}\n{profile.description}\n\nPackages:")
            print("\n".join(f"  {package}" for package in profile.packages))
            if profile.components:
                print("\nExternal components:")
                print("\n".join(f"  {component}" for component in profile.components))
            return 0
        if args.command == "packages":
            print("\n".join(resolve_packages(list(profiles.values()))))
            return 0
        if args.command == "apply":
            selected = _select(args.profiles, profiles)
            return _apply(
                args.profiles,
                resolve_packages(selected),
                resolve_components(selected),
                args.dry_run,
            )
        if args.command == "release-metadata":
            package_inventory = read_dpkg_status(args.dpkg_status) if args.dpkg_status else None
            paths = write_release_metadata(
                profiles.values(),
                args.output_dir,
                args.artifact,
                args.source_date_epoch,
                package_inventory,
            )
            for path in paths:
                print(path)
            return 0
        if STATE_FILE.exists():
            print(STATE_FILE.read_text(encoding="utf-8"), end="")
        else:
            print("No role profiles have been applied with alliectl.")
        return 0
    except (OSError, ProfileError, ReleaseError, subprocess.CalledProcessError, ValueError) as error:
        print(f"alliectl: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

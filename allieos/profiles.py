"""Load and resolve AllieOS role profiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


class ProfileError(ValueError):
    """Raised when profile configuration is invalid."""


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    description: str
    packages: tuple[str, ...]
    components: tuple[str, ...] = ()


def default_profile_dir() -> Path:
    system_path = Path("/usr/share/allieos/profiles")
    if system_path.is_dir():
        return system_path
    return Path(__file__).resolve().parent.parent / "config" / "profiles"


def load_profile(path: Path) -> Profile:
    with path.open("rb") as stream:
        data = tomllib.load(stream)
    profile_id = data.get("id", path.stem)
    name = data.get("name")
    description = data.get("description")
    packages = data.get("packages", [])
    components = data.get("components", [])
    if profile_id != path.stem:
        raise ProfileError(f"{path}: id must match filename")
    if not isinstance(name, str) or not name.strip():
        raise ProfileError(f"{path}: name is required")
    if not isinstance(description, str) or not description.strip():
        raise ProfileError(f"{path}: description is required")
    if not isinstance(packages, list) or not packages:
        raise ProfileError(f"{path}: packages must be a non-empty list")
    if any(not isinstance(item, str) or not item.strip() for item in packages):
        raise ProfileError(f"{path}: package names must be non-empty strings")
    if len(packages) != len(set(packages)):
        raise ProfileError(f"{path}: packages must not contain duplicates")
    if not isinstance(components, list):
        raise ProfileError(f"{path}: components must be a list")
    if any(not isinstance(item, str) or not item.strip() for item in components):
        raise ProfileError(f"{path}: component names must be non-empty strings")
    if len(components) != len(set(components)):
        raise ProfileError(f"{path}: components must not contain duplicates")
    return Profile(profile_id, name.strip(), description.strip(), tuple(packages), tuple(components))


def discover_profiles(profile_dir: Path) -> dict[str, Profile]:
    if not profile_dir.is_dir():
        raise ProfileError(f"profile directory does not exist: {profile_dir}")
    profiles = {profile.id: profile for profile in map(load_profile, profile_dir.glob("*.toml"))}
    if not profiles:
        raise ProfileError(f"no profiles found in {profile_dir}")
    return dict(sorted(profiles.items()))


def resolve_packages(selected: list[Profile]) -> list[str]:
    """Return deterministic de-duplicated package names."""
    return sorted({package for profile in selected for package in profile.packages})


def resolve_components(selected: list[Profile]) -> list[str]:
    """Return deterministic de-duplicated external component identifiers."""
    return sorted({component for profile in selected for component in profile.components})

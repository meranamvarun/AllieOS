"""Generate auditable release metadata for AllieOS artifacts."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Iterable, Mapping, Sequence
from urllib.parse import quote
import uuid

from . import __codename__, __version__
from .profiles import Profile


class ReleaseError(ValueError):
    """Raised when release metadata cannot be generated safely."""


@dataclass(frozen=True)
class PackageMetadata:
    """Version and architecture reported by dpkg for an installed package."""

    version: str
    architecture: str


EXTERNAL_COMPONENTS = {
    "micro-manager": {
        "name": "Micro-Manager",
        "version": "2.0.3",
        "revision": "bba80619603cf8974a0666c06c60ec68111d14b2",
        "source": "https://github.com/micro-manager/micro-manager",
        "purl": "pkg:github/micro-manager/micro-manager@bba80619603cf8974a0666c06c60ec68111d14b2",
    },
    "pathology-platform": {
        "name": "AllieOS Pathology Platform Integration",
        "version": __version__,
        "revision": __version__,
        "source": "NOASSERTION",
        "purl": f"pkg:generic/allieos-pathology-platform@{__version__}",
    }
}


def _timestamp(source_date_epoch: int | None = None) -> str:
    if source_date_epoch is None:
        value = os.environ.get("SOURCE_DATE_EPOCH")
        source_date_epoch = int(value) if value is not None else int(datetime.now(timezone.utc).timestamp())
    return datetime.fromtimestamp(source_date_epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _package_id(name: str) -> str:
    return "SPDXRef-Package-" + re.sub(r"[^A-Za-z0-9.-]", "-", name)


def _inventory(profiles: Iterable[Profile]) -> dict[str, list[str]]:
    membership: dict[str, list[str]] = defaultdict(list)
    for profile in profiles:
        for package in profile.packages:
            membership[package].append(profile.id)
    return {name: sorted(ids) for name, ids in sorted(membership.items())}


def read_dpkg_status(path: Path) -> dict[str, PackageMetadata]:
    """Read installed package versions from a dpkg status database."""
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ReleaseError(f"cannot read dpkg status file {path}: {error}") from error

    packages: dict[str, PackageMetadata] = {}
    for paragraph_number, paragraph in enumerate(re.split(r"\n\s*\n", contents.strip()), 1):
        if not paragraph.strip():
            continue
        fields: dict[str, str] = {}
        current_field: str | None = None
        for line in paragraph.splitlines():
            if line.startswith((" ", "\t")):
                if current_field is None:
                    raise ReleaseError(
                        f"invalid continuation in dpkg status paragraph {paragraph_number}"
                    )
                fields[current_field] += "\n" + line[1:]
                continue
            if ":" not in line:
                raise ReleaseError(f"invalid dpkg status line in paragraph {paragraph_number}: {line}")
            current_field, value = line.split(":", 1)
            fields[current_field] = value.strip()

        if fields.get("Status") != "install ok installed":
            continue
        missing = [field for field in ("Package", "Version", "Architecture") if not fields.get(field)]
        if missing:
            raise ReleaseError(
                f"installed package in dpkg status paragraph {paragraph_number} is missing: "
                + ", ".join(missing)
            )
        name = fields["Package"]
        metadata = PackageMetadata(fields["Version"], fields["Architecture"])
        if name in packages and packages[name] != metadata:
            raise ReleaseError(f"dpkg status contains conflicting installed records for: {name}")
        packages[name] = metadata
    return dict(sorted(packages.items()))


def _package_purl(name: str, metadata: PackageMetadata | None) -> str:
    purl = f"pkg:deb/ubuntu/{quote(name, safe='')}"
    if metadata is not None:
        purl += f"@{quote(metadata.version, safe='')}?arch={quote(metadata.architecture, safe='')}"
    return purl


def build_sboms(
    profiles: Iterable[Profile],
    source_date_epoch: int | None = None,
    package_inventory: Mapping[str, PackageMetadata] | None = None,
) -> tuple[dict, dict]:
    """Build SPDX 2.3 and CycloneDX 1.5 documents from role manifests."""
    profiles = list(profiles)
    inventory = _inventory(profiles)
    if package_inventory is not None:
        missing_packages = sorted(set(inventory) - set(package_inventory))
        if missing_packages:
            raise ReleaseError(
                "declared profile packages are missing from the installed-package inventory: "
                + ", ".join(missing_packages)
            )
    component_membership: dict[str, list[str]] = defaultdict(list)
    for profile in profiles:
        for component in profile.components:
            component_membership[component].append(profile.id)
    created = _timestamp(source_date_epoch)
    fingerprint = json.dumps(
        {
            "packages": inventory,
            "components": component_membership,
            "componentMetadata": EXTERNAL_COMPONENTS,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    document_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"allieos:{__version__}:{fingerprint}")

    spdx_packages = []
    relationships = []
    cyclonedx_components = []
    for name, role_ids in inventory.items():
        spdx_id = _package_id(name)
        metadata = package_inventory.get(name) if package_inventory is not None else None
        purl = _package_purl(name, metadata)
        spdx_package = {
                "SPDXID": spdx_id,
                "name": name,
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": purl,
                    }
                ],
                "annotations": [
                    {
                        "annotationDate": created,
                        "annotationType": "OTHER",
                        "annotator": "Tool: alliectl",
                        "comment": f"Included by profiles: {', '.join(role_ids)}",
                    }
                ],
            }
        if metadata is not None:
            spdx_package["versionInfo"] = metadata.version
            spdx_package["primaryPackagePurpose"] = "APPLICATION"
            spdx_package["annotations"].append(
                {
                    "annotationDate": created,
                    "annotationType": "OTHER",
                    "annotator": "Tool: alliectl",
                    "comment": f"Installed architecture: {metadata.architecture}",
                }
            )
        spdx_packages.append(spdx_package)
        relationships.append(
            {"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": spdx_id}
        )
        cyclonedx_component = {
                "type": "application",
                "bom-ref": purl,
                "name": name,
                "purl": purl,
                "properties": [{"name": "allieos:profiles", "value": ",".join(role_ids)}],
            }
        if metadata is not None:
            cyclonedx_component["version"] = metadata.version
            cyclonedx_component["properties"].append(
                {"name": "allieos:architecture", "value": metadata.architecture}
            )
        cyclonedx_components.append(cyclonedx_component)

    for component_id, role_ids in sorted(component_membership.items()):
        try:
            component = EXTERNAL_COMPONENTS[component_id]
        except KeyError as error:
            raise ReleaseError(f"unknown external component: {component_id}") from error
        name = component["name"]
        version = component["version"]
        revision = component["revision"]
        source = component["source"]
        spdx_id = _package_id(component_id)
        purl = component["purl"]
        spdx_packages.append(
            {
                "SPDXID": spdx_id,
                "name": name,
                "versionInfo": version,
                "downloadLocation": source,
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceType": "purl",
                        "referenceLocator": purl,
                    }
                ],
                "annotations": [
                    {
                        "annotationDate": created,
                        "annotationType": "OTHER",
                        "annotator": "Tool: alliectl",
                        "comment": f"External component included by profiles: {', '.join(sorted(role_ids))}",
                    }
                ],
            }
        )
        relationships.append(
            {"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": spdx_id}
        )
        cyclonedx_component = {
            "type": "application",
            "bom-ref": purl,
            "name": name,
            "version": version,
            "purl": purl,
            "properties": [{"name": "allieos:profiles", "value": ",".join(sorted(role_ids))}],
        }
        if source != "NOASSERTION":
            cyclonedx_component["externalReferences"] = [
                {"type": "vcs", "url": f"{source}@{revision}"}
            ]
        cyclonedx_components.append(cyclonedx_component)

    spdx = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"AllieOS-{__version__}-{__codename__.replace(' ', '-')}-profile-components",
        "documentNamespace": f"https://allieos.invalid/spdx/{document_uuid}",
        "creationInfo": {"created": created, "creators": [f"Tool: alliectl-{__version__}"]},
        "packages": spdx_packages,
        "relationships": relationships,
    }
    cyclonedx = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{document_uuid}",
        "version": 1,
        "metadata": {
            "timestamp": created,
            "tools": {"components": [{"type": "application", "name": "alliectl", "version": __version__}]},
            "component": {
                "type": "operating-system",
                "name": "AllieOS",
                "version": __version__,
                "properties": [{"name": "allieos:codename", "value": __codename__}],
            },
        },
        "components": cyclonedx_components,
    }
    return spdx, cyclonedx


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_release_metadata(
    profiles: Iterable[Profile],
    output_dir: Path,
    artifacts: Sequence[Path] = (),
    source_date_epoch: int | None = None,
    package_inventory: Mapping[str, PackageMetadata] | None = None,
) -> list[Path]:
    """Write both SBOM formats and a checksum manifest, returning created paths."""
    checked_artifacts = [path.resolve() for path in artifacts]
    missing = [str(path) for path in checked_artifacts if not path.is_file()]
    if missing:
        raise ReleaseError(f"artifact does not exist or is not a file: {', '.join(missing)}")
    names = [path.name for path in checked_artifacts]
    if len(names) != len(set(names)):
        raise ReleaseError("artifact filenames must be unique")
    reserved_names = {"allieos.spdx.json", "allieos.cdx.json", "SHA256SUMS"}
    collisions = sorted(set(names) & reserved_names)
    if collisions:
        raise ReleaseError(f"artifact uses a reserved metadata filename: {', '.join(collisions)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    spdx_path = output_dir / "allieos.spdx.json"
    cyclonedx_path = output_dir / "allieos.cdx.json"
    checksum_path = output_dir / "SHA256SUMS"
    spdx, cyclonedx = build_sboms(profiles, source_date_epoch, package_inventory)
    spdx_path.write_text(json.dumps(spdx, indent=2) + "\n", encoding="utf-8")
    cyclonedx_path.write_text(json.dumps(cyclonedx, indent=2) + "\n", encoding="utf-8")

    checksum_targets = [spdx_path, cyclonedx_path, *checked_artifacts]
    checksum_targets.sort(key=lambda path: path.name)
    checksum_path.write_text(
        "".join(f"{_sha256(path)}  {path.name}\n" for path in checksum_targets), encoding="utf-8"
    )
    return [spdx_path, cyclonedx_path, checksum_path]

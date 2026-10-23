"""Generate auditable release metadata for AllieOS artifacts."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Iterable, Sequence
import uuid

from . import __version__
from .profiles import Profile


class ReleaseError(ValueError):
    """Raised when release metadata cannot be generated safely."""


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


def build_sboms(profiles: Iterable[Profile], source_date_epoch: int | None = None) -> tuple[dict, dict]:
    """Build SPDX 2.3 and CycloneDX 1.5 documents from role manifests."""
    inventory = _inventory(profiles)
    created = _timestamp(source_date_epoch)
    fingerprint = json.dumps(inventory, separators=(",", ":"), sort_keys=True)
    document_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"allieos:{__version__}:{fingerprint}")

    spdx_packages = []
    relationships = []
    cyclonedx_components = []
    for name, role_ids in inventory.items():
        spdx_id = _package_id(name)
        purl = f"pkg:deb/ubuntu/{name}"
        spdx_packages.append(
            {
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
        )
        relationships.append(
            {"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": spdx_id}
        )
        cyclonedx_components.append(
            {
                "type": "application",
                "bom-ref": purl,
                "name": name,
                "purl": purl,
                "properties": [{"name": "allieos:profiles", "value": ",".join(role_ids)}],
            }
        )

    spdx = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"AllieOS-{__version__}-profile-packages",
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
            "component": {"type": "operating-system", "name": "AllieOS", "version": __version__},
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
    profiles: Iterable[Profile], output_dir: Path, artifacts: Sequence[Path] = (), source_date_epoch: int | None = None
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
    spdx, cyclonedx = build_sboms(profiles, source_date_epoch)
    spdx_path.write_text(json.dumps(spdx, indent=2) + "\n", encoding="utf-8")
    cyclonedx_path.write_text(json.dumps(cyclonedx, indent=2) + "\n", encoding="utf-8")

    checksum_targets = [spdx_path, cyclonedx_path, *checked_artifacts]
    checksum_targets.sort(key=lambda path: path.name)
    checksum_path.write_text(
        "".join(f"{_sha256(path)}  {path.name}\n" for path in checksum_targets), encoding="utf-8"
    )
    return [spdx_path, cyclonedx_path, checksum_path]

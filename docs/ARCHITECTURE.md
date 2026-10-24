# Architecture

AllieOS is a thin, auditable layer over Ubuntu LTS:

```text
Ubuntu 24.04 LTS + GNOME
        |
        +-- secure base configuration
        +-- AllieOS branding
        +-- alliectl role resolver
                |
                +-- clinician
                +-- pathology-lab
                +-- medical-student
                +-- scientist
                +-- engineer
                +-- technician
```

Profiles are TOML data under `config/profiles`. `alliectl` validates them, combines selected profiles, removes duplicates, and delegates installation to APT. Profiles deliberately contain package names rather than arbitrary shell hooks. System changes that cannot be represented as packages belong in separately reviewed, idempotent configuration modules.

The M0 builder uses Ubuntu's `live-build` packages to create an amd64 evaluation image. Source code, manifests, the union of all profile packages, and Micro-Manager are installed in the image to provide a complete offline pathology workstation. Profiles organize tools by workflow and can reproduce those tool sets on a regular Ubuntu installation. External components use named installers registered in `alliectl`; profile manifests cannot execute arbitrary hooks.

Future third-party applications must include a pinned upstream source, checksum/signature verification, license record, SBOM entry, sandbox decision, update owner, and documented removal path.

## Bundled pathology workflow

The ISO is the AllieOS shining path. It contains the local-first workflow under
`allieos.pathology` together with Ubuntu's Orthanc, DICOMweb, GDCM, and WSI
packages. A desktop launcher starts the workflow service for the signed-in user;
Orthanc supplies the local image archive. The bundle provides the
patient-to-report domain model, immutable report history, tamper-evident audit
chain, metadata lookup, and DICOM WSI references needed for the pathology pilot.

Whole-slide pixels remain in the bundled Orthanc DICOMweb archive rather than
the workflow database. Both services are loopback-only by default. Institutions
must add identity, TLS, durable storage, and validation before remote or clinical
deployment. See [the pathology system design](PATHOLOGY_SYSTEM.md).

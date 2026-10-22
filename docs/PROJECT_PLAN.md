# AllieOS product and delivery plan

## Product outcome

AllieOS should make a safe, maintainable Ubuntu workstation easy to deploy for education, research, pathology imaging, laboratory support, and biomedical engineering. It should reduce setup time without implying that bundled software is automatically suitable for regulated clinical use.

## Users and first workflows

| User | First supported workflows |
| --- | --- |
| Clinician | Review non-diagnostic DICOM, documents, and remote desktops |
| Pathology/lab staff | Inspect whole-slide images, transform images, scan barcodes, handle DICOM files |
| Medical student | Flashcards, reading, writing, statistics, and media |
| Scientist | Python/R notebooks, plots, Git, and rootless containers |
| Engineer | Build software, CAD/EDA, serial devices, and containers |
| Technician | Hardware inventory, storage health, recovery, networking, and serial consoles |

The two technician audiences in the initial brief are represented by `pathology-lab` and `technician`, while profiles remain composable for hybrid jobs.

## Principles

1. Track Ubuntu LTS and upstream security updates; do not fork the kernel without a demonstrated need.
2. Keep the base small and move specialist tools into opt-in profiles.
3. Prefer Ubuntu packages; isolate third-party software and record provenance when it is later introduced.
4. Default to encryption, least privilege, automatic security updates, and no inbound services.
5. Treat patient data as sensitive and keep it out of telemetry, logs, examples, tests, and bug reports.
6. Label every clinical tool as evaluated, research-only, or approved by a deploying institution.

## Milestones

### M0 — Foundation (implemented in this repository)

- Ubuntu 24.04 LTS amd64 live-image recipe.
- Role manifest schema and `alliectl` CLI.
- Initial package sets, branding, security-update defaults, tests, and CI.
- Explicit clinical safety and privacy boundaries.

Exit: tests pass; manifests resolve; every package is available from configured Noble repositories; a live ISO boots in a VM.

### M1 — Installable developer preview

- Integrate and brand Ubuntu Desktop Installer/Subiquity.
- Support UEFI, full-disk encryption, recovery, locale, keyboard, and accessibility.
- Produce reproducible versioned artifacts, SBOMs, checksums, and signed provenance.
- Add automated QEMU boot smoke tests and a hardware compatibility matrix.

Exit: clean VM installs boot reliably, encrypted installation works, and no critical/high image vulnerabilities are untriaged.

### M2 — Pathology pilot

- Validate whole-slide image formats and representative scanner exports.
- Package QuPath/Fiji or alternatives with pinned provenance and license review.
- Add color-management, calibrated-display guidance, anonymized sample data, and DICOM de-identification workflows.
- Pilot with at least one representative from each primary role.

Exit: documented usability study, clinical safety review, privacy threat model, and rollback procedure.

### M3 — Managed fleet beta

- Enterprise identity, VPN, proxy, certificate, disk-escrow, and offline update options.
- Declarative fleet policy, audit logging without patient content, inventory, and remote support consent.
- CIS-oriented hardening profile with compatibility testing.

Exit: staged updates, disaster recovery, 30-day pilot, and administrator runbook are tested.

### M4 — Stable release

- Signed repositories and images, published support lifecycle, incident response, localization, accessibility audit, and upgrade tests from the previous release.
- Institution-specific validation kit; no blanket regulatory or diagnostic claim.

## Near-term backlog

1. Build M0 on Ubuntu and record the first QEMU boot result.
2. Remove or replace packages that fail Noble availability validation.
3. Add ISO checksums and CycloneDX/SPDX SBOM generation.
4. Decide between a Subiquity layer and an OEM/autoinstall deployment path for M1.
5. Recruit workflow owners and gather representative, de-identified file formats and device requirements.
6. Define release signing, governance, trademark, and security-contact ownership.

## Success measures

- New user reaches a role-ready desktop within 30 minutes.
- Critical security updates reach supported images within 48 hours of Ubuntu publication.
- 95% of tested target hardware boots with networking, graphics, storage, and suspend working.
- No patient-identifying data in builds, crash reports, CI, or default telemetry.
- All shipped packages have recorded source, version, license, and update owner.

## Out of scope for the first release

- A new kernel, package manager, or desktop environment.
- Diagnostic claims, medical-device certification, or replacement of institutional validation.
- Hosting an EHR/LIS or central patient database by default.
- Silent telemetry, cloud accounts, or preconfigured remote access.

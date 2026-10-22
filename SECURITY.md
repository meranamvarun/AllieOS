# Security and clinical safety

AllieOS is pre-release software and is not approved for diagnostic or life-critical use.

## Reporting

Do not open a public issue containing credentials, patient information, unreleased vulnerabilities, or identifiable clinical images. Until a private security address is established, repository owners must configure private vulnerability reporting before publishing releases.

## Deployment baseline

- Use full-disk encryption and institution-managed backups.
- Keep automatic security updates enabled and reboot when required.
- Do not expose SSH, DICOM, database, notebook, or remote-desktop services by default.
- Use named non-administrator accounts, screen locking, least privilege, and approved identity policy.
- Disable crash uploads for systems that can encounter patient data unless the collection pipeline has been reviewed.
- Validate displays, scanners, applications, file formats, and end-to-end workflows locally before clinical use.

AllieOS packaging is not evidence that an application is accurate, supported, compliant, or a regulated medical device.

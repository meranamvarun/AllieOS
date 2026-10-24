# AllieOS pathology workflow service

## Status and intended use

This is an evaluation implementation of an anatomic-pathology workflow. It is
not a medical device, has not been validated for primary diagnosis, and must not
be exposed to a network without an institution-approved identity-aware reverse
proxy. The source tree and tests contain synthetic records only.

The service deliberately separates workflow metadata from image pixels:

```text
Authenticated user
       |
       v
AllieOS pathology service ---- DICOM identifiers/deep link ----> WSI viewer
       |                                                       |
       v                                                       v
SQLite evaluation database                          Bundled Orthanc DICOMweb archive
```

AllieOS owns patient lookup, case/accession management, specimen hierarchy,
report versions, sign-out state, and audit events. The bundled Orthanc archive
owns whole-slide image bytes. This avoids duplicating very large images and keeps
the viewer/archive boundary replaceable through DICOM and DICOMweb.

## Implemented workflow

The data hierarchy is:

```text
Patient -> Case/accession -> Specimen -> Block -> Slide -> WSI archive reference
                           -> Report -> Immutable versions
```

The current service supports:

- patients with an MRN and extensible metadata;
- doctors, assignment, referring-doctor details, and case status;
- specimens, blocks, stains, slide labels, DICOM UIDs, and viewer links;
- lookup by MRN, patient name, accession, metadata, doctor, organ, or diagnosis;
- report drafts, sign-out, explicit amendments, and complete version history;
- append-only database triggers for report versions and audit events;
- a SHA-256 hash chain for detecting audit-event alteration;
- a read-only HTML case archive and JSON API;
- local-only binding and PHI-free request logging by default.

## Start an evaluation instance

Use synthetic data only:

```bash
python3 -m allieos.pathology.server \
  --database ./evaluation-pathology.db \
  --viewer-url-template 'https://viewer.example.invalid/?study={study_instance_uid}&series={series_instance_uid}&instance={sop_instance_uid}'
```

Open `http://127.0.0.1:8090`. The server refuses non-loopback bindings. A real
deployment must place it behind an authenticated TLS reverse proxy that sets a
trusted `X-Remote-User` value and removes any client-supplied version of that
header.

Initialize a database without starting the server:

```bash
allie-pathology --database ./evaluation-pathology.db --initialize-only
```

## API walkthrough

Every value below is synthetic. The response IDs from one request are used in
the next request.

```bash
curl -H 'Content-Type: application/json' -H 'X-Remote-User: demo-admin' \
  -d '{"display_name":"Example Pathologist","external_id":"DOC-DEMO-1"}' \
  http://127.0.0.1:8090/api/doctors

curl -H 'Content-Type: application/json' -H 'X-Remote-User: demo-clerk' \
  -d '{"mrn":"DEMO-MRN-1","display_name":"Example Patient","metadata":{"source":"synthetic"}}' \
  http://127.0.0.1:8090/api/patients
```

Create the case, specimen, block, and slide using `POST /api/cases`,
`/api/specimens`, `/api/blocks`, and `/api/slides`. A slide must contain either
an archive-controlled `image_uri` or a DICOM `sop_instance_uid`; DICOM Study and
Series UIDs should also be supplied so the viewer can open the correct context.

Report endpoints are:

- `POST /api/reports/draft`
- `POST /api/reports/sign`
- `POST /api/reports/amend`

Read endpoints are:

- `GET /api/search?q=...&doctor_id=...&status=...`
- `GET /api/patients/{id}`
- `GET /api/cases/{id}`
- `GET /healthz`

The health endpoint includes `audit_chain_valid`. A false value is an incident,
not an invitation to repair the audit table in place.

## Bundled components and licenses

The ISO bundles the workflow and archive stack. Ubuntu packages are resolved by
live-build from the Noble repositories and appear in the generated SPDX and
CycloneDX manifests. AllieOS-owned integration is also an explicit component.

| Component | Role | Upstream license | Boundary and obligation |
| --- | --- | --- | --- |
| AllieOS pathology service | Patient/case workflow and reports | GPL-3.0-only | Modified distributions must meet GPL source and notice requirements. |
| Orthanc core | Bundled DICOM/DICOMweb image archive | GPL-3.0-or-later upstream | Separate process; preserve notices and satisfy corresponding-source obligations for the distributed ISO. |
| Orthanc WSI and official AGPL plugins | Bundled WSI conversion and viewing support | AGPL-3.0-or-later upstream | Publish corresponding source for distributed or network-deployed modifications; obtain legal review for deployment. |
| Slim by Imaging Data Commons | Future alternative DICOMweb viewer | Apache-2.0 | Not currently bundled; preserve copyright, license, NOTICE, and modification notices if added. |
| PostgreSQL, future production store | Durable relational database | PostgreSQL License | Preserve its copyright and permission notices. |
| Keycloak, recommended identity provider | OIDC, roles, and session policy | Apache-2.0 | Preserve license/NOTICE and modifications. |

License identifiers above describe the upstream projects at the time of review;
the exact Ubuntu source package, subcomponents, and bundled libraries must be
checked again before each release. Orthanc packages are represented in the ISO
SBOM. Slim, PostgreSQL, and Keycloak are not currently shipped.

Starling was reviewed as an architectural reference, particularly its separation
of worklist/orchestrator and viewer sessions. It is not embedded because it is a
young multi-service platform and would duplicate the workflow implemented here.

## Production gaps

Do not use this implementation with real patient data until an accountable
institution has addressed at least:

- OIDC authentication, authorization, role separation, session expiry, and
  emergency-access policy;
- PostgreSQL migration, encrypted backups, restore drills, retention, legal
  holds, and disaster recovery;
- end-to-end TLS, disk encryption, secrets management, key rotation, and
  centralized audit export;
- HL7 v2/FHIR order and result interfaces, MPI reconciliation, accession-label
  validation, and scanner reconciliation;
- CAP/RCPath or locally approved synoptic templates, terminology coding, report
  rendering, electronic signatures, addendum policy, and result delivery;
- dual-person verification where required, downtime workflow, concurrency
  controls, accessibility, localization, performance, and cybersecurity testing;
- validation of every scanner format, display, image codec, archive, viewer,
  integration, and AI feature under the applicable jurisdiction and QMS.

AI-generated diagnoses are intentionally absent. A future drafting assistant
must produce a clearly marked proposal, retain its inputs and model provenance,
never sign reports, and require explicit pathologist acceptance.

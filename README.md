# SIH26265 — FDR Management Portal (Foundation)

Starter foundation for SIH26265: Security Deposit / FDR Management Portal.

## Included
- FastAPI application scaffold
- PostgreSQL-ready SQLAlchemy 2.x models
- Institution, user, deposit, financial instrument, document, case, case event,
  verification finding, clearance, release request, notification, and audit entities
- Explicit state-machine transition rules for deposit, case, and release request
- REST endpoints for health, institutions, deposits, and controlled transitions
- Initial Alembic migration
- Pytest tests for workflow rules and initial API authorization boundaries
- Synthetic-data and external-verification safety conventions

## Not included yet
- PostgreSQL Row Level Security policies and database-level tenant isolation
- End-to-end tests against a dedicated Supabase Auth/Storage test project
- Malware scanning, retention/deletion workflows, and orphan-object reconciliation
- Real bank or AICTE integration
- OCR pipeline and email/SMS delivery
- Production deployment configuration and independent security review

Those will be added in later milestones. This foundation must not be represented as an official AICTE system.

## Requirements
- Python 3.11+
- Supabase project (PostgreSQL) or local PostgreSQL for offline development
- pip

## Supabase setup (database connection milestone)
1. Create a Supabase project and open **Project Settings → Database**.
2. Copy the connection string for the backend runtime. Prefer the **session pooler** if your host cannot connect directly to the database over IPv6. Use the direct connection only when your environment supports it.
3. Put the connection string in `.env` as `DATABASE_URL`, using the `postgresql+psycopg://` SQLAlchemy scheme. URL-encode special characters in the database password.
4. Set `DATABASE_SSL_REQUIRED=true`. The app also enables `sslmode=require` when the URL contains `supabase`.
5. Keep `SUPABASE_SERVICE_ROLE_KEY` server-side only. It is not needed for the database-only milestone; Auth and Storage wiring comes next.
6. Run the migration commands below against the Supabase development project first. Do not point a prototype migration at production data.

The engine uses connection health checks and configurable pool limits. If you use Supabase's **transaction pooler**, verify driver/pooling compatibility for your deployment and avoid relying on session-level database state.

## Setup
1. Create a database and a local `.env`:
   ```bash
   copy .env.example .env
   ```
   On Linux/macOS use `cp .env.example .env`.
2. Edit `DATABASE_URL` in `.env`.
3. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Run migrations:
   ```bash
   alembic upgrade head
   ```
5. Start the API:
   ```bash
   uvicorn app.main:app --reload
   ```
6. Open `http://127.0.0.1:8000/docs`.

## Run tests
```bash
pytest
```

## Current workflow rules
### Deposit status
- `DRAFT -> SUBMITTED`
- `SUBMITTED -> UNDER_SCRUTINY`
- `UNDER_SCRUTINY -> CLARIFICATION_REQUIRED | REVIEW_COMPLETE | REJECTED`
- `CLARIFICATION_REQUIRED -> SUBMITTED | REJECTED`
- `REVIEW_COMPLETE -> ACTIVE | REJECTED`
- `ACTIVE -> RENEWAL_PENDING | REPLACEMENT_PENDING | MATURED | CLOSED`
- `RENEWAL_PENDING -> ACTIVE | MATURED | CLOSED`
- `REPLACEMENT_PENDING -> ACTIVE | MATURED | CLOSED`
- `MATURED -> CLOSED`
- Terminal statuses: `CLOSED`, `REJECTED`

These are prototype workflow states, not a substitute for validating every applicable AICTE rule/SOP. Maturity is a lifecycle condition, not release authorization.

### Case status
Cases have their own workflow, separate from the deposit status:
- `OPEN -> ASSIGNED`
- `ASSIGNED -> UNDER_REVIEW`
- `UNDER_REVIEW -> CLARIFICATION_REQUIRED | AWAITING_EXTERNAL_VERIFICATION | READY_FOR_DECISION | REJECTED`
- `CLARIFICATION_REQUIRED -> ASSIGNED | REJECTED`
- `AWAITING_EXTERNAL_VERIFICATION -> UNDER_REVIEW | READY_FOR_DECISION`
- `READY_FOR_DECISION -> COMPLETED | REJECTED`

### Release request status
Release requests have a distinct workflow:
- `DRAFT -> SUBMITTED`
- `SUBMITTED -> DOCUMENT_REVIEW`
- `DOCUMENT_REVIEW -> CLARIFICATION_REQUIRED | AWAITING_CLEARANCES | REJECTED`
- `CLARIFICATION_REQUIRED -> SUBMITTED | REJECTED`
- `AWAITING_CLEARANCES -> READY_FOR_AUTHORITY | REJECTED`
- `READY_FOR_AUTHORITY -> AUTHORITY_ACTION_RECORDED | REJECTED`
- `AUTHORITY_ACTION_RECORDED -> COMPLETED`
- `COMPLETED`, `REJECTED` are terminal.

The release route is represented by `release_method`: `FDR_RPGF` or `RTGS`. The actual authority and documents must be configured against the currently applicable official rules and SOP. The prototype enforces required configured clearances and competent-authority action fields, but it is not a full regulatory checklist and must be reviewed against current official rules.

## Important implementation notes
- Do not store uploaded files in a public directory. `Document.storage_key` is metadata only.
- `AuditEvent` is designed as append-only by application convention; database permissions/triggers and stronger tamper-evidence are needed for production.
- Supabase Auth token validation, application role/institution checks, and private Storage proxy endpoints are implemented. These are not a production security certification. Database RLS policies, dedicated Supabase integration tests, and an independent security review are still required. Do not expose this API publicly until those controls are implemented and tested.
- Demo records/documents must be synthetic and visibly watermarked.
### Dependency and timestamp notes

- ORM timestamp defaults use timezone-aware UTC values (`datetime.now(timezone.utc)`).
- Starlette is constrained below `0.50` to avoid the deprecation warning from its legacy `TestClient` integration with HTTPX. Reinstall dependencies after pulling this change.


## Private Supabase Storage milestone

The API includes authenticated document upload and download endpoints that proxy files through the backend. It does not return public object URLs or signed URLs.

Before testing:
1. In Supabase Storage, create a bucket named `fdr-documents-private` (or set `SUPABASE_STORAGE_BUCKET` to your bucket name).
2. Ensure the bucket is **private**. Do not create a public bucket or grant anonymous read access.
3. Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in the backend `.env`. The service-role key is highly privileged: keep it server-side, never commit it, and never expose it in frontend code or logs.
4. Install dependencies with `python -m pip install -r requirements.txt`.
5. Restart the API after changing `.env`.

Endpoints:
- `POST /api/v1/deposits/{deposit_id}/documents` — multipart fields `document_type` and `file`. Accepts PDF, JPEG, and PNG up to 10 MiB; basic file-signature checks are performed.
- `GET /api/v1/documents/{document_id}/download` — authenticated download proxy; access is checked against the deposit's institution and the caller's role.

Storage keys are generated by the server, not accepted from clients. Uploaded metadata records a SHA-256 checksum and an audit event. Synthetic institutions are explicitly marked as synthetic. The current version stores a single immutable object per upload; document replacement/version-chain management is not yet implemented.

Security limitations to address before production:
- Add Supabase Auth + Storage integration tests against a dedicated test project or a reliable mocked HTTP transport.
- Configure and test least-privilege database access and PostgreSQL RLS; application checks alone are not a database security boundary.
- Add antivirus/content scanning, operational orphan-object reconciliation, retention/deletion policy, rate limits, and comprehensive role matrix tests.
- Review CORS, request-size limits at the reverse proxy, and the exact staff roles permitted to upload/download each document type.
- Confirm the bucket is private in the Supabase dashboard. This API cannot make a public bucket private on its own.


## Release-clearance workflow (Phase 2)

This phase adds API endpoints under `/api/v1/release-requests`:
- `POST /release-requests` — create a release request for an ACTIVE or MATURED deposit; maturity alone never releases a deposit.
- `GET /release-requests` and `GET /release-requests/{id}` — role/institution-scoped reads.
- `POST /release-requests/{id}/clearances/{unit}/assign` — case reviewers or platform admins assign a configured clearance to an active clearance-officer account.
- `POST /release-requests/{id}/clearances/{unit}` — only the assigned clearance officer can record a decision; the release requester cannot decide their own clearance.
- `POST /release-requests/{id}/transition` — controlled state transitions, including a required `CLEARED` decision for every mandatory unit before `READY_FOR_AUTHORITY`, and a required authority reference/date/note before final action can be recorded.

The three clearance units are a conservative prototype baseline, not a claim that they are the complete or universally applicable AICTE clearance list. Confirm the exact units and NOC rules against current official instructions before production use. This prototype records a final authority action; it does not execute a bank transfer or contact AICTE/banks. Do not treat `NOT_APPLICABLE` as a shortcut without a documented policy and authorized review.

Run `python -m pytest -q` in the project virtual environment. This ZIP was assembled from the supplied repository snapshot; full tests could not be executed in the packaging environment because its Python environment does not include the `psycopg` driver. Validate locally before committing.


## Security hardening (Phase 3)

Security-focused API tests cover cross-institution release-request reads, read-only auditor behavior for uploads, denial of financial-document downloads to technical administrators, assignment-gated clearance decisions, unit assignment validation, separation between clearance and final-authority decisions, and denial of `NOT_APPLICABLE` as a shortcut for a mandatory clearance.

Implementation controls added in this phase:
- Release transitions and clearance changes lock the parent release-request row on PostgreSQL to serialize concurrent workflow actions.
- Regulatory clearance and final-authority roles are separate from the platform-admin role.
- Clearance decisions require an explicit assignment to an active clearance-officer account.
- A release requester cannot decide their own clearance or provide the final authority action.
- A clearance decision-maker cannot provide the final authority action for the same release.
- Mandatory clearances must be `CLEARED`; `NOT_APPLICABLE` does not satisfy a mandatory gate.
- Technical administrators are denied document downloads, and auditors are read-only for document upload.

The automated test suite passed in a local SQLite-backed test run (`34 passed`). This is not a live Supabase/PostgreSQL concurrency test and does not replace verification in the project's own `.venv`, tests against Supabase, or an independent security review.

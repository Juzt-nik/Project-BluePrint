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
- Pytest tests for workflow rules
- Synthetic-data and external-verification safety conventions

## Not included yet
- Supabase Auth token validation and application-user provisioning (next milestone)
- Private Supabase Storage upload/download endpoints (next milestone)
- Enforced role-based access and institution-level data isolation (must be implemented before public use)
- Real bank or AICTE integration
- OCR pipeline
- Email/SMS delivery
- Production deployment configuration

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

The release route is represented by `release_method`: `FDR_RPGF` or `RTGS`. The actual authority and documents must be configured against the currently applicable official rules and SOP. The API currently enforces state transitions but does not yet implement a full regulatory checklist/clearance gate. That gate is the next milestone.

## Important implementation notes
- Do not store uploaded files in a public directory. `Document.storage_key` is metadata only.
- `AuditEvent` is designed as append-only by application convention; database permissions/triggers and stronger tamper-evidence are needed for production.
- Database connectivity can be configured for Supabase, but authentication, authorization, institution-level isolation, and private Storage endpoints are not implemented yet. Do not expose this API publicly until those controls are implemented and tested.
- Demo records/documents must be synthetic and visibly watermarked.

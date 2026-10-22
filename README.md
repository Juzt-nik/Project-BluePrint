APP_NAME=SIH26265 FDR Management Portal
ENVIRONMENT=development

# Runtime API connection: dedicated non-owner, non-superuser role with NOBYPASSRLS.
DATABASE_URL=postgresql+psycopg://blueprint_app:APP_PASSWORD@HOST:5432/postgres
# Migration-only connection: schema owner; use only for alembic upgrade head.
MIGRATION_DATABASE_URL=postgresql+psycopg://postgres:MIGRATION_PASSWORD@HOST:5432/postgres
DATABASE_SSL_REQUIRED=true
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=5
DATABASE_POOL_TIMEOUT_SECONDS=30

SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_ANON_KEY=YOUR_SUPABASE_PUBLISHABLE_OR_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_STORAGE_BUCKET=fdr-documents-private

## Phase 5 — Supabase RLS rollout and runtime-role separation

The Phase 4 migration is present in the repository, but it is **not considered applied**
until `alembic_version` reports `20261023_postgres_rls`. Local SQLite tests do not verify
PostgreSQL RLS.

### Required rollout sequence (staging first)

1. Back up the staging database and confirm the existing schema matches the Alembic
   history. The current observed revision before rollout was `fd887e312048`.
2. In Supabase SQL Editor, review `scripts/supabase_runtime_role.sql`. Replace the
   password placeholder with a generated secret only in the SQL editor. Do not put the
   real password in Git, chat, logs, or a committed `.env` file.
3. Run the role bootstrap script as an authorized database administrator. Review grants
   and role flags. The runtime role must not own protected tables, must not be a
   superuser, and must have `rolbypassrls = false`. Do not alter Supabase built-in roles.
4. Configure `DATABASE_URL` to use `blueprint_app` (or the corresponding pooler username
   format shown by Supabase for your connection mode). Configure `MIGRATION_DATABASE_URL`
   separately with the schema-owner/migration connection. Both must remain server-side.
5. Run `python -m alembic upgrade head` with `MIGRATION_DATABASE_URL` set. This migration
   changes PostgreSQL RLS policies; do not apply it to production until the staging
   run and rollback plan have been reviewed.
6. Verify `alembic_version` reports `20261023_postgres_rls`; verify protected tables have
   `relrowsecurity = true` and `relforcerowsecurity = true`; inspect `pg_policies`.
7. Test using the actual `blueprint_app` connection and two test institutions. Confirm
   institution A cannot select, update, or delete institution B's data, including through
   related documents, instruments, cases, release requests, clearances, notifications,
   and audit records.
8. Test Storage separately: private bucket settings and `storage.objects` policies are
   not configured by the database migration in this repository.

### Important implementation caveats

- PostgreSQL RLS context is supplied by the API using transaction-local custom settings.
  This protects against accidental missing tenant filters in normal API paths, but a
  database credential holder who can execute arbitrary SQL as `blueprint_app` may set
  custom GUC values themselves. It is not a defense against compromise of the runtime DB
  credential. Keep credentials secret, restrict network access, and test all policies.
- The policy set currently allows several trusted staff roles cross-institution visibility.
  Confirm this is consistent with the approved operating model before production.
- The role bootstrap script grants CRUD on the listed application tables. Reconcile grants
  with actual endpoints and schema before running; least privilege may require narrower
  grants. `ALTER DEFAULT PRIVILEGES` only affects objects created by the role executing
  that statement, so future migration-owner changes may require repeating the default
  grants as the migration owner.
- Do not give the runtime role ownership of tables. PostgreSQL table owners and roles with
  `BYPASSRLS` can bypass row-level policies unless configuration explicitly prevents it;
  superusers always bypass RLS.

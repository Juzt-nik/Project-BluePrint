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
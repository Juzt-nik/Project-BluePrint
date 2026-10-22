-- Project-BluePrint: least-privilege runtime role bootstrap (Supabase PostgreSQL)
-- Run in Supabase SQL Editor as an authorized database administrator, on STAGING first.
-- Replace the password placeholder with a long random secret. Do not commit the real secret.
-- This role is intentionally NOT a table owner, superuser, or BYPASSRLS role.
-- If the role already exists, review its current attributes before applying ALTER ROLE.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'blueprint_app') THEN
        CREATE ROLE blueprint_app
            LOGIN
            PASSWORD 'REPLACE_WITH_A_LONG_RANDOM_PASSWORD'
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT
            NOREPLICATION
            NOBYPASSRLS;
    END IF;
END
$$;

ALTER ROLE blueprint_app NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO blueprint_app;

-- API CRUD grants. RLS policies remain the row-level security boundary.
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    public.users,
    public.institutions,
    public.deposits,
    public.instruments,
    public.documents,
    public.cases,
    public.case_events,
    public.verification_findings,
    public.release_requests,
    public.clearance_records,
    public.notifications,
    public.audit_events
TO blueprint_app;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO blueprint_app;

-- Keep privileges on future objects created by the migration owner.
-- Execute this ALTER DEFAULT PRIVILEGES as the role that will create future tables.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO blueprint_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO blueprint_app;

-- Verify role flags. Expected: rolsuper=false, rolbypassrls=false.
SELECT rolname, rolsuper, rolbypassrls, rolcanlogin
FROM pg_roles
WHERE rolname = 'blueprint_app';

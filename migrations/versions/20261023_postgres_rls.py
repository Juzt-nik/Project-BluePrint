"""Enable transaction-context-based tenant isolation with PostgreSQL RLS.

The API runtime role must not be a superuser, table owner, or BYPASSRLS role.
Alembic should run with a separate schema-owner connection.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261023_postgres_rls"
down_revision = "fd887e312048"
branch_labels = None
depends_on = None

STAFF = (
    "'admin', 'technical_admin', 'auditor', 'case_officer', "
    "'clearance_officer', 'approval_authority'"
)

def _scope_institution(column: str = "institution_id") -> str:
    return (
        f"({column}::text = NULLIF(current_setting('app.institution_id', true), '') "
        f"OR current_setting('app.role', true) IN ({STAFF}))"
    )

def _scope_deposit(table_alias: str, fk: str = "deposit_id") -> str:
    return (
        f"EXISTS (SELECT 1 FROM deposits d "
        f"WHERE d.id = {table_alias}.{fk} AND {_scope_institution('d.institution_id')})"
    )

def _scope_release(table_alias: str, fk: str = "release_request_id") -> str:
    return (
        f"EXISTS (SELECT 1 FROM release_requests rr "
        f"JOIN deposits d ON d.id = rr.deposit_id "
        f"WHERE rr.id = {table_alias}.{fk} AND {_scope_institution('d.institution_id')})"
    )

def _scope_case(table_alias: str, fk: str = "case_id") -> str:
    return (
        f"EXISTS (SELECT 1 FROM cases c JOIN deposits d ON d.id = c.deposit_id "
        f"WHERE c.id = {table_alias}.{fk} AND {_scope_institution('d.institution_id')})"
    )

POLICIES = {
    "institutions": _scope_institution("id"),
    "deposits": _scope_institution("institution_id"),
    "instruments": _scope_deposit("instruments"),
    "documents": _scope_deposit("documents"),
    "cases": _scope_deposit("cases"),
    "case_events": _scope_case("case_events"),
    "verification_findings": _scope_deposit("verification_findings"),
    "release_requests": _scope_deposit("release_requests"),
    "clearance_records": _scope_release("clearance_records"),
    "audit_events": _scope_institution("institution_id"),
}

def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # Keep SQLite-based unit tests and local development migrations usable.
        return

    # Users require a special SELECT policy because auth lookup happens before the
    # full app user context is known. No general user-table write policy is created.
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS app_users_select ON users")
    op.execute(sa.text("""
        CREATE POLICY app_users_select ON users FOR SELECT USING (
            supabase_auth_user_id::text = NULLIF(current_setting('app.supabase_auth_user_id', true), '')
            OR id::text = NULLIF(current_setting('app.user_id', true), '')
            OR (
                current_setting('app.role', true) IN ('admin', 'case_officer', 'technical_admin')
                AND role = 'clearance_officer'
            )
        )
    """))

    for table, expression in POLICIES.items():
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS app_tenant_scope ON "{table}"')
        op.execute(
            f'CREATE POLICY app_tenant_scope ON "{table}" '
            f'FOR ALL USING ({expression}) WITH CHECK ({expression})'
        )

    # Notifications are recipient-scoped or related to a visible tenant record.
    op.execute("ALTER TABLE notifications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE notifications FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS app_notification_scope ON notifications")
    notification_scope = (
        "(recipient_user_id::text = NULLIF(current_setting('app.user_id', true), '') "
        f"OR current_setting('app.role', true) IN ({STAFF}) "
        "OR (deposit_id IS NOT NULL AND EXISTS (SELECT 1 FROM deposits d "
        f"WHERE d.id = notifications.deposit_id AND {_scope_institution('d.institution_id')})) "
        "OR (release_request_id IS NOT NULL AND EXISTS (SELECT 1 FROM release_requests rr "
        "JOIN deposits d ON d.id = rr.deposit_id "
        f"WHERE rr.id = notifications.release_request_id AND {_scope_institution('d.institution_id')})))"
    )
    op.execute(
        "CREATE POLICY app_notification_scope ON notifications "
        f"FOR ALL USING ({notification_scope}) WITH CHECK ({notification_scope})"
    )

def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in [
        "notifications", "audit_events", "clearance_records", "release_requests",
        "verification_findings", "case_events", "cases", "documents", "instruments",
        "deposits", "institutions", "users"
    ]:
        policy = "app_notification_scope" if table == "notifications" else (
            "app_users_select" if table == "users" else "app_tenant_scope"
        )
        op.execute(f'DROP POLICY IF EXISTS "{policy}" ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')

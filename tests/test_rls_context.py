"""Unit coverage for RLS context setup; PostgreSQL policy behavior needs integration tests."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.security import _set_rls_context


def test_rls_context_helper_is_safe_for_sqlite():
    engine = create_engine("sqlite://")
    with Session(engine) as session:
        _set_rls_context(session, user_id="test-user", institution_id="test-institution", role="institution_representative")
    engine.dispose()

import logging
from typing import Annotated, Callable

import httpx
from fastapi import Depends, HTTPException
from sqlalchemy import event, text
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.entities import User

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)

# Roles are deliberately normalized in one place so UI labels can vary without
# bypassing API authorization. Unknown roles receive no implicit permissions.
ROLE_ALIASES = {
    "institution": "institution_representative",
    "institution_user": "institution_representative",
    "institution_representative": "institution_representative",
    "admin": "admin",
    "technical_admin": "technical_admin",
    "auditor": "auditor",
    "case_officer": "case_officer",
    "scrutiny_officer": "case_officer",
    "clearance_officer": "clearance_officer",
    "approval_authority": "approval_authority",
    "competent_authority": "approval_authority",
}


def normalized_role(user: User) -> str:
    return ROLE_ALIASES.get((user.role or "").strip().lower(), "unknown")


def _apply_rls_context_to_connection(connection, values: dict[str, str | None]) -> None:
    for key, value in values.items():
        connection.execute(
            text("SELECT set_config(:setting_name, :setting_value, true)"),
            {"setting_name": f"app.{key}", "setting_value": value or ""},
        )


@event.listens_for(Session, "after_begin")
def _restore_rls_context_after_transaction(session, transaction, connection) -> None:
    """Reapply transaction-local RLS context after every commit/rollback boundary."""
    values = session.info.get("_app_rls_context")
    if values and connection.dialect.name == "postgresql":
        _apply_rls_context_to_connection(connection, values)


def _set_rls_context(db: Session, **values: str | None) -> None:
    """Set transaction-local PostgreSQL RLS context; SQLite tests intentionally skip it."""
    try:
        dialect = db.get_bind().dialect.name
    except Exception:
        return
    if dialect != "postgresql":
        return
    context = db.info.setdefault("_app_rls_context", {})
    context.update(values)
    # Apply now; the Session event reapplies these values after later commits.
    _apply_rls_context_to_connection(db.connection(), context)


def get_authenticated_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Session = Depends(get_db),
) -> User:
    """Validate a Supabase access token and resolve its active app user."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required.", headers={"WWW-Authenticate": "Bearer"})
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(status_code=503, detail="Authentication is not configured.")

    endpoint = f"{settings.supabase_url.rstrip('/')}/auth/v1/user"
    try:
        response = httpx.get(endpoint, headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {credentials.credentials}"}, timeout=settings.auth_request_timeout_seconds)
    except httpx.RequestError as exc:
        logger.warning("Supabase Auth request failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Authentication service temporarily unavailable.") from exc

    if response.status_code in (401, 403):
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    if response.status_code != 200:
        logger.warning("Supabase Auth returned HTTP %s", response.status_code)
        raise HTTPException(status_code=503, detail="Unable to validate authentication.")
    try:
        auth_user_id = response.json()["id"]
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication response.") from exc

    # The users table itself is RLS-protected, so provide only the verified Supabase
    # identity before the initial app-user lookup. This is transaction-local.
    _set_rls_context(db, supabase_auth_user_id=auth_user_id)
    user = db.query(User).filter(User.supabase_auth_user_id == auth_user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=403, detail="No active application account is linked to this identity.")
    _set_rls_context(
        db,
        user_id=user.id,
        institution_id=user.institution_id,
        role=normalized_role(user),
    )
    return user


def require_roles(*allowed_roles: str) -> Callable:
    allowed = {ROLE_ALIASES.get(role.strip().lower(), role.strip().lower()) for role in allowed_roles}

    def dependency(user: User = Depends(get_authenticated_user)) -> User:
        if normalized_role(user) not in allowed:
            raise HTTPException(status_code=403, detail="You are not permitted to perform this action.")
        return user

    return dependency


def is_institution_user(user: User) -> bool:
    return normalized_role(user) == "institution_representative"


def can_review_deposits(user: User) -> bool:
    return normalized_role(user) in {"case_officer", "approval_authority"}

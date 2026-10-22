
import logging
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.entities import User

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


def get_authenticated_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    db: Session = Depends(get_db),
) -> User:
    """Validate a Supabase access token and resolve its active app user."""

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(
            status_code=503,
            detail="Authentication is not configured.",
        )

    token = credentials.credentials
    endpoint = f"{settings.supabase_url.rstrip('/')}/auth/v1/user"

    try:
        response = httpx.get(
            endpoint,
            headers={
                "apikey": settings.supabase_anon_key,
                "Authorization": f"Bearer {token}",
            },
            timeout=settings.auth_request_timeout_seconds,
        )
    except httpx.RequestError as exc:
        logger.warning("Supabase Auth request failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Authentication service temporarily unavailable.",
        ) from exc

    if response.status_code == 401 or response.status_code == 403:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    if response.status_code != 200:
        logger.warning("Supabase Auth returned HTTP %s", response.status_code)
        raise HTTPException(
            status_code=503,
            detail="Unable to validate authentication.",
        )

    try:
        auth_user = response.json()
        auth_user_id = auth_user["id"]
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication response.",
        ) from exc

    user = (
        db.query(User)
        .filter(User.supabase_auth_user_id == auth_user_id)
        .first()
    )

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="No active application account is linked to this identity.",
        )

    return user

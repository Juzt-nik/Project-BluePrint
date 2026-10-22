"""Private Supabase Storage REST client.

Files are proxied through the API; this module never generates public URLs.
"""
from __future__ import annotations

import httpx
from fastapi import HTTPException

from app.core.config import settings


def _storage_config() -> tuple[str, str]:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(status_code=503, detail="Private document storage is not configured.")
    return settings.supabase_url.rstrip("/"), settings.supabase_service_role_key


def upload_private_object(key: str, content: bytes, content_type: str) -> None:
    base, secret = _storage_config()
    url = f"{base}/storage/v1/object/{settings.supabase_storage_bucket}/{key}"
    try:
        response = httpx.post(
            url,
            headers={
                "apikey": secret,
                "Authorization": f"Bearer {secret}",
                "Content-Type": content_type,
                "x-upsert": "false",
            },
            content=content,
            timeout=20.0,
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Document storage is temporarily unavailable.") from exc
    if response.status_code not in (200, 201):
        # Never expose upstream response bodies or credentials to clients.
        raise HTTPException(status_code=502, detail="Document could not be stored securely.")


def download_private_object(key: str) -> tuple[bytes, str]:
    base, secret = _storage_config()
    url = f"{base}/storage/v1/object/{settings.supabase_storage_bucket}/{key}"
    try:
        response = httpx.get(
            url,
            headers={"apikey": secret, "Authorization": f"Bearer {secret}"},
            timeout=20.0,
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Document storage is temporarily unavailable.") from exc
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Stored document not found.")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Document could not be retrieved securely.")
    return response.content, response.headers.get("content-type", "application/octet-stream")

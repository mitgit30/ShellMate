import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

from backend.app.core.config import get_settings


def require_api_key(
    api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Protect application routes with a shared API key.

    ShellMate currently has no user/account model, so a shared API key is a
    deliberate intermediate step before introducing JWT users and ownership.
    """
    configured_key = get_settings().shellmate_api_key
    if not configured_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured.",
        )
    if not api_key or not secrets.compare_digest(api_key, configured_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )

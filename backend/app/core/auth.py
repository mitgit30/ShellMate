import logging
import secrets
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from backend.app.core.config import get_settings

logger = logging.getLogger(__name__)


def require_api_key(
    request: Request,
    api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Protect application routes with a shared API key.

    ShellMate currently has no user/account model, so a shared API key is a
    deliberate intermediate step before introducing JWT users and ownership.
    """
    configured_key = get_settings().shellmate_api_key
    if not configured_key:
        logger.error("api_auth_unavailable path=%s", request.url.path)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured.",
        )
    if not api_key or not secrets.compare_digest(api_key, configured_key):
        logger.warning(
            "api_auth_rejected path=%s client=%s",
            request.url.path,
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )

import logging
import secrets
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from backend.app.core.config import get_settings
from backend.app.repositories.user_repository import User

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


def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> User:
    """Resolve the logged-in user; API key remains a temporary compatibility path."""
    repository = request.app.state.user_repository
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        user = repository.get_user_by_token(token)
        if user:
            return user
    settings = get_settings()
    if api_key and settings.shellmate_api_key and secrets.compare_digest(api_key, settings.shellmate_api_key):
        return repository.ensure_user(settings.local_auth_email, settings.local_auth_password)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

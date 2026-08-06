from datetime import timedelta

import logging
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from backend.app.api.dependencies import user_repository
from backend.app.core.config import get_settings
from backend.app.schemas.auth import LoginRequest, LoginResponse, RegisterRequest
from backend.app.api.dependencies import server_repository

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _issue_token(user) -> LoginResponse:
    lifetime = timedelta(minutes=get_settings().auth_token_lifetime_minutes)
    token = user_repository.create_session(user.id, lifetime)
    return LoginResponse(
        access_token=token,
        expires_in=int(lifetime.total_seconds()),
        user_id=user.id,
        email=user.email,
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    user = user_repository.authenticate(payload.email, payload.password)
    if user is None:
        logger.warning("auth_login_failed email=%s", payload.email.strip().lower())
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    logger.info("auth_login_succeeded user_id=%s", user.id)
    return _issue_token(user)


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> LoginResponse:
    try:
        user = user_repository.create_user(payload.email, payload.password)
    except ValueError as exc:
        logger.warning("auth_account_creation_rejected email=%s", payload.email.strip().lower())
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    # Assign legacy unowned records to the first account created after migration.
    server_repository.assign_unowned_servers(user.id)
    logger.info("auth_account_created user_id=%s", user.id)
    return _issue_token(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        user = user_repository.get_user_by_token(token)
        user_repository.revoke_session(token)
        if user:
            logger.info("auth_logout user_id=%s", user.id)

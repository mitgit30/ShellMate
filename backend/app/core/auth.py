from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from backend.app.repositories.user_repository import User

def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Resolve the user from the bearer token issued at login."""
    repository = request.app.state.user_repository
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        user = repository.get_user_by_token(token)
        if user:
            return user
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

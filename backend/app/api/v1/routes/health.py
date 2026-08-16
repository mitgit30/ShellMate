import logging

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from backend.app.api.dependencies import database

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def readiness_check() -> JSONResponse | dict[str, str]:
    """Report whether the backend can currently reach its database."""
    try:
        with database.connect() as connection:
            connection.execute("SELECT 1")
    except Exception:
        logger.exception("database_readiness_check_failed")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "database": "unavailable",
                "detail": "The database is temporarily unavailable.",
            },
        )
    return {"status": "ready", "database": "available"}

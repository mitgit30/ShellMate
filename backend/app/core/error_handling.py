"""Shared error-to-HTTP mapping and diagnostic helpers."""

import logging
from collections.abc import Mapping

from sqlalchemy.exc import OperationalError

from backend.app.core.exceptions import SSHConnectionError, ServerNotFoundError


def status_code_for_exception(exc: Exception) -> int:
    if isinstance(exc, ServerNotFoundError):
        return 404
    if isinstance(exc, SSHConnectionError):
        return 502
    if isinstance(exc, OperationalError):
        return 503
    if isinstance(exc, ValueError):
        return 400
    return 500


def public_error_message(exc: Exception) -> str:
    if status_code_for_exception(exc) == 503:
        return "The database is temporarily unavailable. Please try again shortly."
    if status_code_for_exception(exc) == 500:
        return "The server could not complete the request. Check the backend logs for details."
    return str(exc) or "The request could not be completed."


def log_exception(
    logger: logging.Logger,
    operation: str,
    exc: Exception,
    context: Mapping[str, object] | None = None,
) -> None:
    """Log a concise production message and keep the traceback at DEBUG."""
    details = {key: value for key, value in (context or {}).items() if value is not None}
    context_text = f" context={details!r}" if details else ""
    logger.error("%s failed%s error=%s", operation, context_text, _compact_error(exc))
    logger.debug("%s traceback%s", operation, context_text, exc_info=exc)


def _compact_error(exc: Exception, limit: int = 500) -> str:
    """Make an exception useful in a one-line log record."""
    message = " ".join(str(exc).split())
    return (message or type(exc).__name__)[:limit]

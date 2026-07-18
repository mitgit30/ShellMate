"""Shared error-to-HTTP mapping and diagnostic helpers."""

import logging
from collections.abc import Mapping

from backend.app.core.exceptions import SSHConnectionError, ServerNotFoundError


def status_code_for_exception(exc: Exception) -> int:
    if isinstance(exc, ServerNotFoundError):
        return 404
    if isinstance(exc, SSHConnectionError):
        return 502
    if isinstance(exc, ValueError):
        return 400
    return 500


def public_error_message(exc: Exception) -> str:
    if status_code_for_exception(exc) == 500:
        return "The server could not complete the request. Check the backend logs for details."
    return str(exc) or "The request could not be completed."


def log_exception(
    logger: logging.Logger,
    operation: str,
    exc: Exception,
    context: Mapping[str, object] | None = None,
) -> None:
    details = {key: value for key, value in (context or {}).items() if value is not None}
    logger.exception("%s failed%s", operation, f" context={details!r}" if details else "")
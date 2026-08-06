"""Application logging configuration."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 3


_CONFIGURED = False
_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(request_id: str):
    return _request_id.set(request_id)


def reset_request_id(token) -> None:
    _request_id.reset(token)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


def configure_logging(
    log_directory: Path = Path("logs"),
    level: str | int = logging.INFO,
    enable_file_logging: bool = True,
) -> None:
    """Configure console logging and optional rotating file logging.

    Console output remains enabled for containers and hosted environments.
    File logging is useful for local development and can be disabled with
    ``LOG_FILE_ENABLED=false`` when a platform collects stdout instead.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    resolved_level = _resolve_log_level(level)
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if enable_file_logging:
        log_directory.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_directory / "app.log",
                maxBytes=DEFAULT_MAX_BYTES,
                backupCount=DEFAULT_BACKUP_COUNT,
                encoding="utf-8",
            )
        )

    for handler in handlers:
        handler.addFilter(RequestIdFilter())
    logging.basicConfig(level=resolved_level, format=LOG_FORMAT, handlers=handlers)
    _CONFIGURED = True


def _resolve_log_level(level: str | int) -> int:
    if isinstance(level, int):
        return level

    resolved = logging.getLevelNamesMapping().get(level.upper())
    if not isinstance(resolved, int):
        raise ValueError(f"Unknown log level: {level}")
    return resolved

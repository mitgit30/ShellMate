import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1.routes.chat import router as chat_router
from backend.app.api.v1.routes.commands import router as commands_router
from backend.app.api.v1.routes.health import router as health_router
from backend.app.api.v1.routes.keys import router as keys_router
from backend.app.api.v1.routes.servers import router as servers_router
from backend.app.api.v1.routes.sessions import router as sessions_router
from backend.app.core.config import get_settings
from backend.app.core.error_handling import log_exception, public_error_message, status_code_for_exception
from backend.app.core.logging_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(title=settings.api_title, version=settings.api_version)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log_exception(logger, "unhandled API request", exc, {"method": request.method, "path": request.url.path})
    return JSONResponse(status_code=status_code_for_exception(exc), content={"detail": public_error_message(exc)})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(keys_router, prefix="/api/v1")
app.include_router(servers_router, prefix="/api/v1")
app.include_router(sessions_router, prefix="/api/v1")
app.include_router(commands_router, prefix="/api/v1")



from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1.routes.commands import router as commands_router
from backend.app.api.v1.routes.health import router as health_router
from backend.app.api.v1.routes.keys import router as keys_router
from backend.app.api.v1.routes.servers import router as servers_router
from backend.app.api.v1.routes.sessions import router as sessions_router
from backend.app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.api_title, version=settings.api_version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(keys_router, prefix="/api/v1")
app.include_router(servers_router, prefix="/api/v1")
app.include_router(sessions_router, prefix="/api/v1")
app.include_router(commands_router, prefix="/api/v1")

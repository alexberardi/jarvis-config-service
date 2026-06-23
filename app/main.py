from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from jarvis_settings_client import create_settings_router, create_superuser_auth

from app.config import get_settings
from app.routes import services_router
from app.routes.service_registration import create_service_registration_router
from app.routes.settings_gateway import create_settings_gateway_router
from app.services.settings_service import get_settings_service

# Create superuser auth dependency (module-level so tests can override it)
_cfg = get_settings()
superuser_auth = create_superuser_auth(_cfg.JARVIS_AUTH_URL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is owned solely by Alembic now — the startup entrypoint runs
    # `alembic upgrade head` before the app boots. We deliberately do NOT call
    # Base.metadata.create_all() here: it only CREATES missing tables (never
    # ALTERs), so it silently diverged from the migrations and caused the
    # 2026-06 services.external_host drift. Alembic is the single source of truth.
    yield
    # Shutdown: nothing to clean up


app = FastAPI(
    title="Jarvis Config Service",
    description="Central service registry for the Jarvis ecosystem",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: wildcard origin is acceptable here because every endpoint authenticates
# via header (bearer JWT / admin token), not cookies. With no cookies in play,
# credentials mode adds nothing but the "*"+credentials combo browsers reject — off.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service registry routes
app.include_router(services_router)

# Config service's own settings routes (superuser JWT auth)
_settings_router = create_settings_router(
    service=get_settings_service(),
    auth_dependency=superuser_auth,
)
app.include_router(_settings_router, prefix="/settings", tags=["settings"])

# Service registration routes (superuser JWT auth)
_registration_router = create_service_registration_router(
    superuser_auth_dependency=superuser_auth,
)
app.include_router(_registration_router)

# Settings gateway routes (superuser JWT auth, proxies to all services)
_gateway_router = create_settings_gateway_router(
    superuser_auth_dependency=superuser_auth,
)
app.include_router(_gateway_router)


@app.get("/info")
def info():
    """Unauthenticated service identity endpoint for network discovery."""
    return {"service": "jarvis-config-service"}


@app.get("/health")
def health():
    """Health check for the config service itself."""
    return {"status": "ok"}


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)

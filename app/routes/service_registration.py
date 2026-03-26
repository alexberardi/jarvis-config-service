"""Service registration router: bulk-register services in config DB and jarvis-auth."""

import hmac
import re
import time
from pathlib import Path
from typing import Any, Callable

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.known_services import KNOWN_SERVICES
from app.models import Service
from app.schemas import (
    HealthProbeRequest,
    HealthProbeResponse,
    KnownServiceEntry,
    KeyRotateRequest,
    KeyRotateResponse,
    ServiceRegisterItem,
    ServiceRegisterRequest,
    ServiceRegisterResponse,
    ServiceRegisterResult,
    ServiceRegistryResponse,
)


async def _admin_token_or_superuser(
    request: Request,
    superuser_auth_dependency: Callable[..., Any],
) -> dict:
    """Accept either X-Jarvis-Admin-Token header or superuser JWT.

    This allows first-boot registration before any users exist.
    """
    admin_token = request.headers.get("X-Jarvis-Admin-Token")
    if admin_token:
        settings = get_settings()
        if not settings.JARVIS_AUTH_ADMIN_TOKEN:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="JARVIS_AUTH_ADMIN_TOKEN not configured on config-service",
            )
        if hmac.compare_digest(admin_token, settings.JARVIS_AUTH_ADMIN_TOKEN):
            return {"sub": "admin-token", "is_superuser": True}
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token",
        )
    # Fall back to superuser JWT — call with the Authorization header string,
    # not the Request object (the dependency expects authorization: str)
    authorization = request.headers.get("Authorization")
    return superuser_auth_dependency(authorization=authorization)


def create_service_registration_router(
    superuser_auth_dependency: Callable[..., Any],
) -> APIRouter:
    """Factory that returns a router with the given superuser auth dependency."""

    router = APIRouter(prefix="/v1/services", tags=["service-registration"])

    async def either_auth(request: Request) -> dict:
        return await _admin_token_or_superuser(request, superuser_auth_dependency)

    @router.get("/registry", response_model=ServiceRegistryResponse)
    async def get_service_registry(
        db: Session = Depends(get_db),
        _user: dict = Depends(either_auth),
    ) -> ServiceRegistryResponse:
        """Return known services with their config-DB and auth registration status."""
        settings = get_settings()

        # Load all Service rows from config DB, keyed by name
        db_services: dict[str, Service] = {
            s.name: s for s in db.query(Service).all()
        }

        # Fetch existing app-clients from jarvis-auth
        auth_app_ids: set[str] = set()
        if settings.JARVIS_AUTH_ADMIN_TOKEN:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        f"{settings.JARVIS_AUTH_URL}/admin/app-clients",
                        headers={"X-Jarvis-Admin-Token": settings.JARVIS_AUTH_ADMIN_TOKEN},
                    )
                    if resp.status_code == 200:
                        for entry in resp.json():
                            auth_app_ids.add(entry["app_id"])
            except httpx.RequestError:
                pass  # auth service unreachable; auth_registered will be False

        entries: list[KnownServiceEntry] = []
        for ks in KNOWN_SERVICES:
            name = str(ks["name"])
            db_svc = db_services.get(name)
            entries.append(
                KnownServiceEntry(
                    name=name,
                    default_port=int(ks["port"]),
                    description=str(ks["description"]),
                    health_path=str(ks["health_path"]),
                    config_registered=db_svc is not None,
                    auth_registered=name in auth_app_ids,
                    current_host=db_svc.host if db_svc else None,
                    current_port=db_svc.port if db_svc else None,
                    current_scheme=db_svc.scheme if db_svc else None,
                )
            )

        return ServiceRegistryResponse(
            services=entries,
            jarvis_root=settings.JARVIS_ROOT or None,
        )

    @router.post("/register", response_model=ServiceRegisterResponse)
    async def register_services(
        body: ServiceRegisterRequest,
        db: Session = Depends(get_db),
        _user: dict = Depends(either_auth),
    ) -> ServiceRegisterResponse:
        """Bulk-register services in config DB and jarvis-auth."""
        settings = get_settings()

        if not settings.JARVIS_AUTH_ADMIN_TOKEN:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="JARVIS_AUTH_ADMIN_TOKEN not configured on config-service",
            )

        # Build a lookup of known services for descriptions / health paths
        known_map: dict[str, dict[str, str | int]] = {
            str(ks["name"]): ks for ks in KNOWN_SERVICES
        }

        # Fetch existing auth app-clients once for the entire batch
        existing_auth_ids = await _fetch_auth_app_ids(settings)

        results: list[ServiceRegisterResult] = []

        for item in body.services:
            result = await _register_one(
                item, db, settings, known_map, existing_auth_ids,
            )

            # Write .env file if base_path (or JARVIS_ROOT) available and we have an app_key
            effective_base_path = body.base_path or settings.JARVIS_ROOT
            if effective_base_path and result.app_key:
                result.env_written = _write_env_file(
                    effective_base_path, item.name, result.app_key, result,
                )

            results.append(result)

        return ServiceRegisterResponse(results=results)

    @router.post("/rotate-key", response_model=KeyRotateResponse)
    async def rotate_service_key(
        body: KeyRotateRequest,
        _user: dict = Depends(either_auth),
    ) -> KeyRotateResponse:
        """Rotate an app-client key in jarvis-auth, optionally write to .env."""
        settings = get_settings()

        if not settings.JARVIS_AUTH_ADMIN_TOKEN:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="JARVIS_AUTH_ADMIN_TOKEN not configured on config-service",
            )

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{settings.JARVIS_AUTH_URL}/admin/app-clients/{body.service_name}/rotate",
                    headers={"X-Jarvis-Admin-Token": settings.JARVIS_AUTH_ADMIN_TOKEN},
                )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Auth service error: {exc}",
            )

        if resp.status_code != 200:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Auth rotate failed: {resp.text}",
            )

        new_key: str = resp.json()["key"]

        env_written: bool | None = None
        if body.base_path:
            # Use a temporary result object for error reporting
            tmp_result = ServiceRegisterResult(
                name=body.service_name,
                config_ok=True,
                auth_ok=True,
                auth_created=False,
            )
            env_written = _write_env_file(
                body.base_path, body.service_name, new_key, tmp_result,
            )

        return KeyRotateResponse(
            service_name=body.service_name,
            app_key=new_key,
            env_written=env_written,
        )

    @router.post("/probe", response_model=HealthProbeResponse)
    async def probe_service_health(
        body: HealthProbeRequest,
        _user: dict = Depends(either_auth),
    ) -> HealthProbeResponse:
        """Probe a service's health endpoint at an arbitrary host:port."""
        settings = get_settings()
        probe_host = body.host
        if probe_host in ("localhost", "127.0.0.1") and settings.DOCKER_HOST_GATEWAY:
            probe_host = settings.DOCKER_HOST_GATEWAY
        url = f"{body.scheme}://{probe_host}:{body.port}{body.health_path}"
        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(url)
                latency_ms = round((time.time() - start) * 1000, 1)
                if resp.status_code == 200:
                    return HealthProbeResponse(healthy=True, latency_ms=latency_ms)
                return HealthProbeResponse(
                    healthy=False, latency_ms=latency_ms,
                    error=f"HTTP {resp.status_code}",
                )
        except httpx.ConnectError:
            return HealthProbeResponse(healthy=False, error="Connection refused")
        except httpx.TimeoutException:
            return HealthProbeResponse(healthy=False, error="Timeout")
        except httpx.RequestError as exc:
            return HealthProbeResponse(healthy=False, error=str(exc))

    return router


async def _fetch_auth_app_ids(settings: Any) -> set[str]:
    """Fetch the set of existing app-client IDs from jarvis-auth."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{settings.JARVIS_AUTH_URL}/admin/app-clients",
                headers={"X-Jarvis-Admin-Token": settings.JARVIS_AUTH_ADMIN_TOKEN},
            )
            if resp.status_code == 200:
                return {entry["app_id"] for entry in resp.json()}
    except httpx.RequestError:
        pass
    return set()


async def _register_one(
    item: ServiceRegisterItem,
    db: Session,
    settings: Any,
    known_map: dict[str, dict[str, str | int]],
    existing_auth_ids: set[str],
) -> ServiceRegisterResult:
    """Register a single service in config DB + jarvis-auth."""
    config_ok = False
    auth_ok = False
    auth_created = False
    app_key: str | None = None
    error: str | None = None

    # 1. Upsert in config DB
    try:
        known = known_map.get(item.name, {})
        existing = db.query(Service).filter(Service.name == item.name).first()
        if existing:
            existing.host = item.host
            existing.port = item.port
            existing.scheme = item.scheme
        else:
            db.add(
                Service(
                    name=item.name,
                    host=item.host,
                    port=item.port,
                    scheme=item.scheme,
                    health_path=str(known.get("health_path", "/health")),
                    description=str(known.get("description", "")),
                )
            )
        db.commit()
        config_ok = True
    except Exception as exc:
        error = f"Config DB error: {exc}"
        db.rollback()
        return ServiceRegisterResult(
            name=item.name,
            config_ok=config_ok,
            auth_ok=auth_ok,
            auth_created=auth_created,
            app_key=app_key,
            error=error,
        )

    # 2. Create app-client in jarvis-auth (if not already present)
    if item.name in existing_auth_ids:
        auth_ok = True
        auth_created = False
    else:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                create_resp = await client.post(
                    f"{settings.JARVIS_AUTH_URL}/admin/app-clients",
                    json={"app_id": item.name, "name": item.name},
                    headers={"X-Jarvis-Admin-Token": settings.JARVIS_AUTH_ADMIN_TOKEN},
                )
                if create_resp.status_code == 201:
                    auth_ok = True
                    auth_created = True
                    app_key = create_resp.json().get("key")
                else:
                    error = f"Auth create failed: HTTP {create_resp.status_code}"
        except httpx.RequestError as exc:
            error = f"Auth service error: {exc}"

    return ServiceRegisterResult(
        name=item.name,
        config_ok=config_ok,
        auth_ok=auth_ok,
        auth_created=auth_created,
        app_key=app_key,
        error=error,
    )


def _write_env_file(
    base_path: str,
    service_name: str,
    app_key: str,
    result: ServiceRegisterResult,
    config_url: str | None = None,
) -> bool:
    """Write or update JARVIS_APP_ID, JARVIS_APP_KEY, and JARVIS_CONFIG_URL in a service's .env file.

    Returns True on success, False on failure (appends error to result).
    """
    env_path = Path(base_path) / service_name / ".env"

    try:
        env_path.parent.mkdir(parents=True, exist_ok=True)

        new_vars: dict[str, str] = {
            "JARVIS_APP_ID": service_name,
            "JARVIS_APP_KEY": app_key,
        }
        if config_url:
            new_vars["JARVIS_CONFIG_URL"] = config_url

        if env_path.exists():
            content = env_path.read_text()
            for var_name, var_value in new_vars.items():
                pattern = re.compile(rf"^{var_name}=.*$", re.MULTILINE)
                if pattern.search(content):
                    content = pattern.sub(f"{var_name}={var_value}", content)
                else:
                    if content and not content.endswith("\n"):
                        content += "\n"
                    content += f"{var_name}={var_value}\n"
            env_path.write_text(content)
        else:
            lines = [f"{k}={v}" for k, v in new_vars.items()]
            env_path.write_text("\n".join(lines) + "\n")

        return True
    except OSError as exc:
        existing_error = result.error
        env_error = f".env write failed: {exc}"
        result.error = f"{existing_error}; {env_error}" if existing_error else env_error
        return False

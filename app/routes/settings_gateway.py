"""Settings gateway routes.

Aggregates settings from all registered services and proxies writes.
Protected by superuser JWT auth.
"""

import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Service
from app.schemas import (
    AggregatedSettingsResponse,
    ServiceSettingsResult,
    ServiceUpdateResponse,
)


def create_settings_gateway_router(
    superuser_auth_dependency: Any,
) -> APIRouter:
    """Create the settings gateway router with the given auth dependency.

    Args:
        superuser_auth_dependency: FastAPI dependency that validates superuser JWT.
    """
    router = APIRouter(prefix="/v1/settings", tags=["settings-gateway"])

    async def _fetch_service_settings(
        client: httpx.AsyncClient,
        service: Service,
        app_id: str,
        app_key: str,
        auth_header: str | None = None,
    ) -> ServiceSettingsResult | None:
        """Fetch settings from a single service using JWT and/or app-to-app auth."""
        dockerized = bool(get_settings().DOCKER_HOST_GATEWAY)
        url = f"{service.get_url(dockerized=dockerized)}/settings/"
        headers: dict[str, str] = {}
        if auth_header:
            headers["Authorization"] = auth_header
        if app_id and app_key:
            headers["X-Jarvis-App-Id"] = app_id
            headers["X-Jarvis-App-Key"] = app_key

        start = time.time()
        try:
            resp = await client.get(url, headers=headers)
            latency_ms = round((time.time() - start) * 1000, 2)

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception:
                    # Empty or non-JSON 200 response — treat as no settings
                    return None
                return ServiceSettingsResult(
                    service_name=service.name,
                    success=True,
                    settings=data.get("settings", []),
                    latency_ms=latency_ms,
                )
            elif resp.status_code == 404:
                # Service has no settings endpoint — exclude from results
                return None
            else:
                return ServiceSettingsResult(
                    service_name=service.name,
                    success=False,
                    settings=[],
                    error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                    latency_ms=latency_ms,
                )
        except httpx.ConnectError:
            latency_ms = round((time.time() - start) * 1000, 2)
            return ServiceSettingsResult(
                service_name=service.name,
                success=False,
                settings=[],
                error="Connection refused",
                latency_ms=latency_ms,
            )
        except httpx.TimeoutException:
            latency_ms = round((time.time() - start) * 1000, 2)
            return ServiceSettingsResult(
                service_name=service.name,
                success=False,
                settings=[],
                error="Timeout",
                latency_ms=latency_ms,
            )
        except httpx.RequestError as exc:
            latency_ms = round((time.time() - start) * 1000, 2)
            return ServiceSettingsResult(
                service_name=service.name,
                success=False,
                settings=[],
                error=f"{type(exc).__name__}: {exc}",
                latency_ms=latency_ms,
            )

    @router.get("/", response_model=AggregatedSettingsResponse)
    async def get_aggregated_settings(
        request: Request,
        service: str | None = Query(None, description="Filter to a specific service name"),
        db: Session = Depends(get_db),
        _auth: Any = Depends(superuser_auth_dependency),
    ) -> AggregatedSettingsResponse:
        """Aggregate settings from all registered services (or a specific one).

        Requires superuser JWT. Fans out to each service using app-to-app auth.
        """
        cfg = get_settings()

        query = db.query(Service)
        if service:
            query = query.filter(Service.name == service)
        services = query.order_by(Service.name).all()

        if service and not services:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service '{service}' not found in registry",
            )

        auth_header = request.headers.get("authorization")

        results: list[ServiceSettingsResult] = []
        async with httpx.AsyncClient(timeout=cfg.SETTINGS_GATEWAY_TIMEOUT) as client:
            for svc in services:
                result = await _fetch_service_settings(
                    client, svc, cfg.JARVIS_APP_ID, cfg.JARVIS_APP_KEY,
                    auth_header=auth_header,
                )
                # None means service has no settings endpoint (404) — skip it
                if result is not None:
                    results.append(result)

        successful = sum(1 for r in results if r.success)
        return AggregatedSettingsResponse(
            services=results,
            total_services=len(results),
            successful_services=successful,
            failed_services=len(results) - successful,
        )

    @router.put("/{service_name}/{key:path}", response_model=ServiceUpdateResponse)
    async def update_service_setting(
        service_name: str,
        key: str,
        request: Request,
        db: Session = Depends(get_db),
        _auth: Any = Depends(superuser_auth_dependency),
    ) -> ServiceUpdateResponse:
        """Proxy a settings write to a specific service.

        Requires superuser JWT. Forwards both JWT and app-to-app credentials.
        """
        cfg = get_settings()

        svc = db.query(Service).filter(Service.name == service_name).first()
        if not svc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service '{service_name}' not found in registry",
            )

        body = await request.json()

        # Forward JWT + app-to-app headers
        headers: dict[str, str] = {"Content-Type": "application/json"}
        auth_header = request.headers.get("authorization")
        if auth_header:
            headers["Authorization"] = auth_header
        if cfg.JARVIS_APP_ID and cfg.JARVIS_APP_KEY:
            headers["X-Jarvis-App-Id"] = cfg.JARVIS_APP_ID
            headers["X-Jarvis-App-Key"] = cfg.JARVIS_APP_KEY

        dockerized = bool(cfg.DOCKER_HOST_GATEWAY)
        url = f"{svc.get_url(dockerized=dockerized)}/settings/{key}"
        try:
            async with httpx.AsyncClient(timeout=cfg.SETTINGS_GATEWAY_TIMEOUT) as client:
                resp = await client.put(url, json=body, headers=headers)
        except httpx.RequestError as exc:
            return ServiceUpdateResponse(
                service_name=service_name,
                success=False,
                key=key,
                requires_reload=False,
                error=f"Failed to reach {service_name}: {type(exc).__name__}: {exc}",
            )

        if resp.status_code == 200:
            data = resp.json()
            return ServiceUpdateResponse(
                service_name=service_name,
                success=data.get("success", True),
                key=data.get("key", key),
                requires_reload=data.get("requires_reload", False),
                message=data.get("message"),
            )
        else:
            return ServiceUpdateResponse(
                service_name=service_name,
                success=False,
                key=key,
                requires_reload=False,
                error=f"HTTP {resp.status_code}: {resp.text[:200]}",
            )

    return router

import os
import time
from enum import Enum
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Service
from app.schemas import (
    ServiceCreate,
    ServiceUpdate,
    ServiceResponse,
    ServiceListResponse,
    ServiceHealthStatus,
    AllServicesHealthResponse,
)
from app.auth import require_admin
from app.config import get_settings

router = APIRouter(prefix="/services", tags=["services"])


class UrlStyle(str, Enum):
    """URL style for service responses."""
    default = "default"
    dockerized = "dockerized"
    remote = "remote"
    external = "external"


def _resolve_url_params(
    style: Optional[UrlStyle],
    remote_host: Optional[str],
) -> tuple[bool, str | None, bool]:
    """Resolve style + remote_host into (dockerized, effective_remote_host, external)."""
    if style == UrlStyle.external:
        # External clients (mobile / off the docker network): use the published
        # coords, and swap a localhost external_host for the caller's host if given.
        effective_host = remote_host or os.getenv("JARVIS_REMOTE_HOST")
        return False, effective_host, True
    if style == UrlStyle.remote:
        # A caller on another machine must use the PUBLISHED coords, so resolve
        # against external_host/external_port like `external` does. In bridge
        # mode host/port hold container coords (auth-api:8000) which mean
        # nothing off this host; external_host is the "localhost" sentinel that
        # gets rewritten to effective_host just below.
        #
        # Rows registered before external_* existed have them NULL and fall
        # back to host/port, which is why the backfill migration matters.
        effective_host = remote_host or os.getenv("JARVIS_REMOTE_HOST")
        return False, effective_host, True
    return style == UrlStyle.dockerized, None, False


def _service_url(
    s: Service, dockerized: bool, remote_host: str | None, external: bool = False
) -> str:
    """Get the URL for a service given resolved style params."""
    return s.get_url(dockerized=dockerized, remote_host=remote_host, external=external)


@router.get("", response_model=ServiceListResponse)
def list_services(
    style: Optional[UrlStyle] = Query(default=None, description="URL style: 'dockerized' or 'remote'"),
    remote_host: Optional[str] = Query(default=None, description="Remote host IP (used with style=remote)"),
    db: Session = Depends(get_db),
):
    """
    List all registered services.

    Query Parameters:
        style: URL style. 'dockerized' replaces localhost with host.docker.internal.
               'remote' replaces localhost with remote_host IP.
        remote_host: IP/hostname for remote style (falls back to JARVIS_REMOTE_HOST env).
    """
    dockerized, effective_remote_host, external = _resolve_url_params(style, remote_host)
    services = db.query(Service).order_by(Service.name).all()
    return ServiceListResponse(
        services=[
            ServiceResponse(
                id=s.id,
                name=s.name,
                host=s.host,
                port=s.port,
                scheme=s.scheme,
                health_path=s.health_path,
                description=s.description,
                external_host=s.external_host,
                external_port=s.external_port,
                url=_service_url(s, dockerized, effective_remote_host, external),
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in services
        ]
    )


@router.get("/health", response_model=AllServicesHealthResponse)
async def check_all_services_health(db: Session = Depends(get_db)):
    """Check health of all registered services."""
    settings = get_settings()
    services = db.query(Service).all()
    
    results = {}
    healthy_count = 0
    
    async with httpx.AsyncClient(timeout=settings.HEALTH_CHECK_TIMEOUT) as client:
        for service in services:
            start = time.time()
            try:
                response = await client.get(service.health_url)
                latency_ms = (time.time() - start) * 1000
                
                if response.status_code == 200:
                    results[service.name] = ServiceHealthStatus(
                        healthy=True,
                        latency_ms=round(latency_ms, 2)
                    )
                    healthy_count += 1
                else:
                    results[service.name] = ServiceHealthStatus(
                        healthy=False,
                        latency_ms=round(latency_ms, 2),
                        error=f"HTTP {response.status_code}"
                    )
            except httpx.ConnectError:
                results[service.name] = ServiceHealthStatus(
                    healthy=False,
                    error="Connection refused"
                )
            except httpx.TimeoutException:
                results[service.name] = ServiceHealthStatus(
                    healthy=False,
                    error="Timeout"
                )
            except httpx.RequestError as e:
                results[service.name] = ServiceHealthStatus(
                    healthy=False,
                    error=f"{type(e).__name__}: {e}"
                )
    
    return AllServicesHealthResponse(
        services=results,
        healthy_count=healthy_count,
        total_count=len(services)
    )


@router.get("/{name}", response_model=ServiceResponse)
def get_service(
    name: str,
    style: Optional[UrlStyle] = Query(default=None, description="URL style: 'dockerized' or 'remote'"),
    remote_host: Optional[str] = Query(default=None, description="Remote host IP (used with style=remote)"),
    db: Session = Depends(get_db),
):
    """Get a specific service by name."""
    dockerized, effective_remote_host, external = _resolve_url_params(style, remote_host)
    service = db.query(Service).filter(Service.name == name).first()
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{name}' not found"
        )
    return ServiceResponse(
        id=service.id,
        name=service.name,
        host=service.host,
        port=service.port,
        scheme=service.scheme,
        health_path=service.health_path,
        description=service.description,
        external_host=service.external_host,
        external_port=service.external_port,
        url=_service_url(service, dockerized, effective_remote_host, external),
        created_at=service.created_at,
        updated_at=service.updated_at,
    )


@router.get("/{name}/health", response_model=ServiceHealthStatus)
async def check_service_health(name: str, db: Session = Depends(get_db)):
    """Check health of a specific service."""
    settings = get_settings()
    service = db.query(Service).filter(Service.name == name).first()
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{name}' not found"
        )
    
    start = time.time()
    async with httpx.AsyncClient(timeout=settings.HEALTH_CHECK_TIMEOUT) as client:
        try:
            response = await client.get(service.health_url)
            latency_ms = (time.time() - start) * 1000
            
            if response.status_code == 200:
                return ServiceHealthStatus(
                    healthy=True,
                    latency_ms=round(latency_ms, 2)
                )
            else:
                return ServiceHealthStatus(
                    healthy=False,
                    latency_ms=round(latency_ms, 2),
                    error=f"HTTP {response.status_code}"
                )
        except httpx.ConnectError:
            return ServiceHealthStatus(healthy=False, error="Connection refused")
        except httpx.TimeoutException:
            return ServiceHealthStatus(healthy=False, error="Timeout")
        except httpx.RequestError as e:
            return ServiceHealthStatus(healthy=False, error=f"{type(e).__name__}: {e}")


@router.post("", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
def create_service(
    service: ServiceCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin),
):
    """Register a new service. Requires admin token."""
    existing = db.query(Service).filter(Service.name == service.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Service '{service.name}' already exists"
        )

    db_service = Service(
        name=service.name,
        host=service.host,
        port=service.port,
        scheme=service.scheme,
        health_path=service.health_path,
        description=service.description,
    )
    db.add(db_service)
    db.commit()
    db.refresh(db_service)

    return ServiceResponse(
        id=db_service.id,
        name=db_service.name,
        host=db_service.host,
        port=db_service.port,
        scheme=db_service.scheme,
        health_path=db_service.health_path,
        description=db_service.description,
        url=db_service.url,
        created_at=db_service.created_at,
        updated_at=db_service.updated_at,
    )


@router.put("/{name}", response_model=ServiceResponse)
def update_service(
    name: str,
    update: ServiceUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin),
):
    """Update a service. Requires admin token."""
    service = db.query(Service).filter(Service.name == name).first()
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{name}' not found"
        )

    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(service, field, value)

    db.commit()
    db.refresh(service)

    return ServiceResponse(
        id=service.id,
        name=service.name,
        host=service.host,
        port=service.port,
        scheme=service.scheme,
        health_path=service.health_path,
        description=service.description,
        url=service.url,
        created_at=service.created_at,
        updated_at=service.updated_at,
    )


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(
    name: str,
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin),
):
    """Delete a service. Requires admin token."""
    service = db.query(Service).filter(Service.name == name).first()
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{name}' not found"
        )
    
    db.delete(service)
    db.commit()

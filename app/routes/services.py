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


@router.get("", response_model=ServiceListResponse)
def list_services(
    style: Optional[UrlStyle] = Query(default=None, description="URL style: 'dockerized' replaces localhost with host.docker.internal"),
    db: Session = Depends(get_db),
):
    """
    List all registered services.

    Query Parameters:
        style: URL style. Use 'dockerized' for Docker containers to get
               host.docker.internal instead of localhost/127.0.0.1.
    """
    dockerized = style == UrlStyle.dockerized
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
                url=s.get_url(dockerized=dockerized),
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
    style: Optional[UrlStyle] = Query(default=None, description="URL style: 'dockerized' replaces localhost with host.docker.internal"),
    db: Session = Depends(get_db),
):
    """Get a specific service by name."""
    dockerized = style == UrlStyle.dockerized
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
        url=service.get_url(dockerized=dockerized),
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

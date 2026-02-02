from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ServiceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(..., ge=1, le=65535)
    scheme: str = Field(default="http", pattern="^(https?|mqtts?)$", max_length=10)
    health_path: str = Field(default="/health", max_length=255)
    description: Optional[str] = Field(default=None, max_length=500)


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    host: Optional[str] = Field(default=None, min_length=1, max_length=255)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    scheme: Optional[str] = Field(default=None, pattern="^(https?|mqtts?)$", max_length=10)
    health_path: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=500)


class ServiceResponse(ServiceBase):
    id: int
    url: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ServiceListResponse(BaseModel):
    services: list[ServiceResponse]


class ServiceHealthStatus(BaseModel):
    healthy: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class AllServicesHealthResponse(BaseModel):
    services: dict[str, ServiceHealthStatus]
    healthy_count: int
    total_count: int

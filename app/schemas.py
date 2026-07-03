import re

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


_BARE_HOST_RE = re.compile(r"[A-Za-z0-9._-]+")


def validate_host(v: Optional[str]) -> Optional[str]:
    """Reject anything that isn't a bare hostname / IP literal.

    A registered ``host`` is handed to every service as a discovery target, so a
    value carrying a scheme, path, port, credentials, or whitespace
    (``http://evil``, ``evil/../x``, ``h:1234``, ``u@h``) could redirect callers
    or smuggle a second URL. Only accept a bare host: letters, digits, ``.``,
    ``-``, ``_`` — or a ``[…]``-bracketed IPv6 literal. Port/scheme are separate
    fields; IP-range policy (SSRF) is out of scope for format validation.
    """
    if v is None:
        return v
    s = v.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1]
        if re.fullmatch(r"[0-9A-Fa-f:.]+", inner):
            return s
        raise ValueError("invalid IPv6 host literal")
    if not _BARE_HOST_RE.fullmatch(s):
        raise ValueError(
            "host must be a bare hostname or IP (letters, digits, '.', '-', '_') "
            "with no scheme, path, port, '@', or whitespace"
        )
    return s


class ServiceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(..., ge=1, le=65535)
    scheme: str = Field(default="http", pattern="^(https?|mqtts?|wss?)$", max_length=10)
    health_path: str = Field(default="/health", max_length=255)
    description: Optional[str] = Field(default=None, max_length=500)

    _v_host = field_validator("host")(validate_host)


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    host: Optional[str] = Field(default=None, min_length=1, max_length=255)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    scheme: Optional[str] = Field(default=None, pattern="^(https?|mqtts?|wss?)$", max_length=10)
    health_path: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=500)

    _v_host = field_validator("host")(validate_host)


class ServiceResponse(ServiceBase):
    id: int
    url: str
    external_host: Optional[str] = None
    external_port: Optional[int] = None
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


# ── Settings Gateway ──


class ServiceSettingsResult(BaseModel):
    service_name: str
    success: bool
    settings: list[dict]
    error: Optional[str] = None
    latency_ms: Optional[float] = None


class AggregatedSettingsResponse(BaseModel):
    services: list[ServiceSettingsResult]
    total_services: int
    successful_services: int
    failed_services: int


class ServiceUpdateResponse(BaseModel):
    service_name: str
    success: bool
    key: str
    requires_reload: bool
    message: Optional[str] = None
    error: Optional[str] = None


# ── Service Registration ──


class KnownServiceEntry(BaseModel):
    name: str
    default_port: int
    description: str
    health_path: str
    config_registered: bool
    auth_registered: bool
    current_host: Optional[str] = None
    current_port: Optional[int] = None
    current_scheme: Optional[str] = None
    custom: bool = False


class ServiceRegistryResponse(BaseModel):
    services: list[KnownServiceEntry]
    jarvis_root: str | None = None  # In-container path to jarvis root (if mounted)


class ServiceRegisterItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    host: str = Field(default="localhost", min_length=1, max_length=255)
    port: int = Field(..., ge=1, le=65535)
    scheme: str = Field(default="http", pattern="^(https?|mqtts?|wss?)$", max_length=10)
    health_path: str = Field(default="/health", max_length=255)
    description: Optional[str] = Field(default=None, max_length=500)
    # Externally-reachable coords for off-docker clients (mobile). Optional;
    # falls back to host/port. external_host is typically "localhost" (a
    # sentinel the client/`?style=external` rewrites to the reachable host).
    external_host: Optional[str] = Field(default=None, max_length=255)
    external_port: Optional[int] = Field(default=None, ge=1, le=65535)

    _v_host = field_validator("host", "external_host")(validate_host)


class ServiceRegisterRequest(BaseModel):
    services: list[ServiceRegisterItem]
    base_path: Optional[str] = Field(
        default=None,
        description="Base directory for Jarvis services (e.g. /home/alex/jarvis). "
        "When set, writes JARVIS_APP_ID and JARVIS_APP_KEY to each service's .env file.",
    )


class ServiceRegisterResult(BaseModel):
    name: str
    config_ok: bool
    auth_ok: bool
    auth_created: bool
    app_key: Optional[str] = None
    env_written: Optional[bool] = None
    error: Optional[str] = None


class ServiceRegisterResponse(BaseModel):
    results: list[ServiceRegisterResult]


class HealthProbeRequest(BaseModel):
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(..., ge=1, le=65535)
    health_path: str = Field(default="/health", max_length=255)
    scheme: str = Field(default="http", pattern="^https?$", max_length=5)

    _v_host = field_validator("host")(validate_host)


class HealthProbeResponse(BaseModel):
    healthy: bool
    latency_ms: float | None = None
    error: str | None = None


class KeyRotateRequest(BaseModel):
    service_name: str = Field(..., min_length=1, max_length=64)
    base_path: Optional[str] = Field(
        default=None,
        description="Base directory for Jarvis services. "
        "When set, writes the new JARVIS_APP_KEY to the service's .env file.",
    )


class KeyRotateResponse(BaseModel):
    service_name: str
    app_key: str
    env_written: Optional[bool] = None

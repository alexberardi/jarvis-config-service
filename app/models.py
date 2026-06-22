from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, UniqueConstraint, func
from app.database import Base


class Setting(Base):
    """Settings table for runtime configuration with multi-tenant support."""

    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(255), nullable=False, index=True)
    value = Column(Text, nullable=True)  # JSON-encoded value
    value_type = Column(String(50), nullable=False, default="string")
    category = Column(String(100), nullable=False, default="general", index=True)
    description = Column(Text, nullable=True)
    requires_reload = Column(Boolean, default=False)
    is_secret = Column(Boolean, default=False)
    env_fallback = Column(String(255), nullable=True)

    # Multi-tenant scoping (all nullable = system default)
    household_id = Column(String(255), nullable=True, index=True)
    node_id = Column(String(255), nullable=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "key", "household_id", "node_id", "user_id", name="uq_setting_scope"
        ),
    )


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), unique=True, nullable=False, index=True)
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    scheme = Column(String(10), default="http", nullable=False)
    health_path = Column(String(255), default="/health")
    description = Column(String(500), nullable=True)
    # Externally-reachable coordinates for clients OFF the docker network (the
    # mobile app on a phone). host/port above stay the container coords for
    # direct container-to-container discovery; these are the published host +
    # published port an external client should use. Nullable — fall back to
    # host/port when unset.
    external_host = Column(String(255), nullable=True)
    external_port = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def get_url(
        self,
        dockerized: bool = False,
        remote_host: str | None = None,
        external: bool = False,
    ) -> str:
        """
        Get the service URL.

        Args:
            dockerized: If True and host is localhost/127.0.0.1,
                       replace with host.docker.internal
            remote_host: If set and host is localhost/127.0.0.1,
                        replace with this remote IP/hostname
            external: If True, use the externally-reachable coordinates
                     (external_host/external_port), falling back to host/port.
                     For clients off the docker network (mobile).
        """
        host = (self.external_host or self.host) if external else self.host
        port = (self.external_port or self.port) if external else self.port
        if remote_host and host in ("localhost", "127.0.0.1"):
            host = remote_host
        elif dockerized and host in ("localhost", "127.0.0.1"):
            host = "host.docker.internal"
        return f"{self.scheme}://{host}:{port}"

    @property
    def url(self) -> str:
        """Default URL (non-dockerized)."""
        return self.get_url(dockerized=False)

    def get_health_url(self, dockerized: bool = False, remote_host: str | None = None) -> str:
        """Get the health check URL."""
        return f"{self.get_url(dockerized, remote_host)}{self.health_path}"

    @property
    def health_url(self) -> str:
        """Default health URL (non-dockerized)."""
        return self.get_health_url(dockerized=False)

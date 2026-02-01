from sqlalchemy import Column, Integer, String, DateTime, func
from app.database import Base


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), unique=True, nullable=False, index=True)
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    scheme = Column(String(10), default="http", nullable=False)
    health_path = Column(String(255), default="/health")
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def get_url(self, dockerized: bool = False) -> str:
        """
        Get the service URL.

        Args:
            dockerized: If True and host is localhost/127.0.0.1,
                       replace with host.docker.internal
        """
        host = self.host
        if dockerized and host in ("localhost", "127.0.0.1"):
            host = "host.docker.internal"
        return f"{self.scheme}://{host}:{self.port}"

    @property
    def url(self) -> str:
        """Default URL (non-dockerized)."""
        return self.get_url(dockerized=False)

    def get_health_url(self, dockerized: bool = False) -> str:
        """Get the health check URL."""
        return f"{self.get_url(dockerized)}{self.health_path}"

    @property
    def health_url(self) -> str:
        """Default health URL (non-dockerized)."""
        return self.get_health_url(dockerized=False)

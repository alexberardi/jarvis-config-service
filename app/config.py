import os
from functools import lru_cache


class Settings:
    # Database URLs
    # DB_URL: used when running in Docker (host.docker.internal)
    # MIGRATIONS_DATABASE_URL: used for local dev and migrations (localhost)
    DB_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/jarvis_config")
    MIGRATIONS_DATABASE_URL: str = os.getenv("MIGRATIONS_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/jarvis_config")

    ADMIN_TOKEN: str = os.getenv("JARVIS_CONFIG_ADMIN_TOKEN", "")
    PORT: int = int(os.getenv("JARVIS_CONFIG_PORT", os.getenv("PORT", "8013")))
    HOST: str = os.getenv("HOST", "0.0.0.0")

    # Health check settings
    HEALTH_CHECK_TIMEOUT: float = float(os.getenv("HEALTH_CHECK_TIMEOUT", "5.0"))

    # App-to-app credentials (for calling other services' settings endpoints)
    JARVIS_APP_ID: str = os.getenv("JARVIS_APP_ID", "")
    JARVIS_APP_KEY: str = os.getenv("JARVIS_APP_KEY", "")

    # Auth service URL (for JWT validation)
    JARVIS_AUTH_URL: str = os.getenv("JARVIS_AUTH_URL", "http://localhost:8007")

    # Admin token for jarvis-auth admin endpoints (app-client management)
    JARVIS_AUTH_ADMIN_TOKEN: str = os.getenv("JARVIS_AUTH_ADMIN_TOKEN", "")

    # Timeout for settings gateway fan-out calls
    SETTINGS_GATEWAY_TIMEOUT: float = float(os.getenv("SETTINGS_GATEWAY_TIMEOUT", "10.0"))

    # When running in Docker, set to "host.docker.internal" so that probes
    # targeting "localhost" are rewritten to reach the host machine.
    DOCKER_HOST_GATEWAY: str = os.getenv("DOCKER_HOST_GATEWAY", "")

    # In-container path to the jarvis root (volume-mounted from host).
    # Used as default base_path for writing .env files during service registration.
    JARVIS_ROOT: str = os.getenv("JARVIS_ROOT", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()

import os
from functools import lru_cache

# Shipped-template values (and common variants) that must never act as a real
# admin token — this service bootstraps the whole cluster.
PLACEHOLDER_TOKENS = {
    "",
    "change-me",
    "changeme",
    "change_me",
    "__set_me__",
    "change-me-to-something-secure",
    "change_me_config_admin_token",
}


def is_placeholder_token(value: str | None) -> bool:
    return (value or "").strip().lower() in PLACEHOLDER_TOKENS


class Settings:
    # Database URLs
    # DB_URL: used when running in Docker (host.docker.internal)
    # MIGRATIONS_DATABASE_URL: used for local dev and migrations (localhost)
    DB_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/jarvis_config")
    MIGRATIONS_DATABASE_URL: str = os.getenv("MIGRATIONS_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/jarvis_config")

    ADMIN_TOKEN: str = os.getenv("JARVIS_CONFIG_ADMIN_TOKEN", "")
    PORT: int = int(os.getenv("JARVIS_CONFIG_PORT", os.getenv("PORT", "7700")))
    HOST: str = os.getenv("HOST", "0.0.0.0")

    JARVIS_ENV: str = os.getenv("JARVIS_ENV", "")

    @property
    def is_production(self) -> bool:
        return self.JARVIS_ENV.strip().lower() in {"production", "prod"}

    def insecure_secrets(self) -> list[str]:
        """Names of security-critical secrets that are empty, a known placeholder,
        or too short to be safe. Empty list = all good.

        ``ADMIN_TOKEN`` gates every write to the service registry — a placeholder
        here means anyone can repoint service URLs for the whole cluster.
        """
        token = (self.ADMIN_TOKEN or "").strip()
        if is_placeholder_token(token) or len(token) < 16:
            return ["JARVIS_CONFIG_ADMIN_TOKEN"]
        return []

    # Health check settings
    HEALTH_CHECK_TIMEOUT: float = float(os.getenv("HEALTH_CHECK_TIMEOUT", "5.0"))

    # App-to-app credentials (for calling other services' settings endpoints)
    JARVIS_APP_ID: str = os.getenv("JARVIS_APP_ID", "")
    JARVIS_APP_KEY: str = os.getenv("JARVIS_APP_KEY", "")

    # Auth service URL (for JWT validation)
    JARVIS_AUTH_URL: str = os.getenv("JARVIS_AUTH_URL", "http://localhost:7701")

    # Admin token for jarvis-auth admin endpoints (app-client management)
    JARVIS_AUTH_ADMIN_TOKEN: str = os.getenv("JARVIS_AUTH_ADMIN_TOKEN", "")

    # Timeout for settings gateway fan-out calls
    SETTINGS_GATEWAY_TIMEOUT: float = float(os.getenv("SETTINGS_GATEWAY_TIMEOUT", "10.0"))

    # When running in Docker, set to "host.docker.internal" so that probes
    # targeting "localhost" are rewritten to reach the host machine.
    DOCKER_HOST_GATEWAY: str = os.getenv("DOCKER_HOST_GATEWAY", "")

    # When using style=remote, fall back to this host if no remote_host query param
    JARVIS_REMOTE_HOST: str = os.getenv("JARVIS_REMOTE_HOST", "")

    # In-container path to the jarvis root (volume-mounted from host).
    # Used as default base_path for writing .env files during service registration.
    JARVIS_ROOT: str = os.getenv("JARVIS_ROOT", "")


def enforce_secret_security(cfg: Settings, log) -> None:
    """Warn on insecure secrets everywhere; abort startup only in production."""
    problems = cfg.insecure_secrets()
    if not problems:
        return
    detail = (
        ", ".join(problems)
        + " is empty, a known placeholder, or shorter than 16 chars. Set a strong "
        "random value (e.g. `openssl rand -hex 32`)."
    )
    if cfg.is_production:
        raise RuntimeError(f"Refusing to start in production — insecure admin config: {detail}")
    log.warning(
        "⚠️  Insecure admin config: " + detail
        + "  (set JARVIS_ENV=production to make this fatal)"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

import os
from functools import lru_cache


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/jarvis_config")
    ADMIN_TOKEN: str = os.getenv("JARVIS_CONFIG_ADMIN_TOKEN", "")
    PORT: int = int(os.getenv("PORT", "8013"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    
    # Health check settings
    HEALTH_CHECK_TIMEOUT: float = float(os.getenv("HEALTH_CHECK_TIMEOUT", "5.0"))


@lru_cache
def get_settings() -> Settings:
    return Settings()

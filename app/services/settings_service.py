"""Settings service for jarvis-config-service.

Provides runtime configuration that can be modified without restarting.
Settings are stored in the database with fallback to environment variables.
Uses the shared jarvis-settings-client library.
"""

import logging

from jarvis_settings_client import SettingDefinition, SettingsService

logger = logging.getLogger(__name__)


# Config service settings definitions
SETTINGS_DEFINITIONS: list[SettingDefinition] = [
    SettingDefinition(
        key="health_check.timeout",
        category="health_check",
        value_type="float",
        default=5.0,
        description="Timeout in seconds for health check requests",
        env_fallback="HEALTH_CHECK_TIMEOUT",
    ),
    SettingDefinition(
        key="health_check.enabled",
        category="health_check",
        value_type="bool",
        default=True,
        description="Whether health checks are enabled",
        env_fallback="HEALTH_CHECK_ENABLED",
    ),
]


# Global singleton
_settings_service: SettingsService | None = None


def get_settings_service() -> SettingsService:
    """Get the global SettingsService instance."""
    global _settings_service
    if _settings_service is None:
        from app.models import Setting
        from app.database import SessionLocal

        _settings_service = SettingsService(
            definitions=SETTINGS_DEFINITIONS,
            get_db_session=SessionLocal,
            setting_model=Setting,
        )
    return _settings_service

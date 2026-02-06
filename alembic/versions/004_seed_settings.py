"""Seed default settings

Revision ID: 004
Revises: 003
Create Date: 2026-02-05 16:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


# Settings definitions from app/services/settings_service.py
SETTINGS = [
    {
        "key": "health_check.timeout",
        "value": "5.0",
        "value_type": "float",
        "category": "health_check",
        "description": "Timeout in seconds for health check requests",
        "env_fallback": "HEALTH_CHECK_TIMEOUT",
        "requires_reload": False,
        "is_secret": False,
    },
    {
        "key": "health_check.enabled",
        "value": "true",
        "value_type": "bool",
        "category": "health_check",
        "description": "Whether health checks are enabled",
        "env_fallback": "HEALTH_CHECK_ENABLED",
        "requires_reload": False,
        "is_secret": False,
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == 'postgresql'

    for setting in SETTINGS:
        if is_postgres:
            conn.execute(
                sa.text("""
                    INSERT INTO settings (key, value, value_type, category, description,
                                         env_fallback, requires_reload, is_secret,
                                         household_id, node_id, user_id)
                    VALUES (:key, :value, :value_type, :category, :description,
                           :env_fallback, :requires_reload, :is_secret,
                           NULL, NULL, NULL)
                    ON CONFLICT (key, household_id, node_id, user_id) DO NOTHING
                """),
                setting
            )
        else:
            conn.execute(
                sa.text("""
                    INSERT OR IGNORE INTO settings (key, value, value_type, category, description,
                                                   env_fallback, requires_reload, is_secret,
                                                   household_id, node_id, user_id)
                    VALUES (:key, :value, :value_type, :category, :description,
                           :env_fallback, :requires_reload, :is_secret,
                           NULL, NULL, NULL)
                """),
                setting
            )


def downgrade() -> None:
    conn = op.get_bind()
    for setting in SETTINGS:
        conn.execute(
            sa.text("""
                DELETE FROM settings
                WHERE key = :key
                  AND household_id IS NULL
                  AND node_id IS NULL
                  AND user_id IS NULL
            """),
            {"key": setting["key"]}
        )

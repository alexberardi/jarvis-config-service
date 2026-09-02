"""backfill external_host / external_port from host / port

Revision ID: 006
Revises: 005
Create Date: 2026-09-01

Migration 005 added external_host/external_port but left existing rows NULL,
and Service.get_url() falls back to host/port when they are unset.

That fallback was harmless while host/port held published coords. It stops
being harmless now that ?style=remote resolves against the external coords
(routes/services.py::_resolve_url_params) and the CLI registers container
coords (auth-api:8000) in host/port for bridge mode: a remote caller hitting a
NULL external_host would fall back to a container DNS name that means nothing
off this host.

Backfilling from the current host/port preserves exactly what those rows
resolved to before, so upgrading is a no-op for anyone already running. Rows
are then corrected on the next ./jarvis start --all, which re-registers with
both coordinate pairs set explicitly.

Only touches rows where the columns are still NULL — re-runnable, and it will
not clobber coords that were set deliberately.
"""
from typing import Sequence, Union

from alembic import op


revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE services
           SET external_host = COALESCE(external_host, host),
               external_port = COALESCE(external_port, port)
         WHERE external_host IS NULL
            OR external_port IS NULL
        """
    )


def downgrade() -> None:
    # Restoring NULLs would be guesswork — a backfilled value is
    # indistinguishable from a deliberately-set one — and re-registration
    # repopulates these anyway. Intentionally a no-op.
    pass

"""Tests for the legacy-DB Alembic bootstrap (2026-06 external_host incident).

config-service historically created its tables via ``Base.metadata.create_all()``
with NO alembic stamp, so existing/prod DBs have the tables but an EMPTY
``alembic_version``. A bare ``alembic upgrade head`` (run by the new startup
entrypoint) would start from migration 001 and crash re-creating ``services``.
``stamp_legacy_db_if_needed`` stamps such DBs with the right baseline first.
"""

import os
import sys

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine

# The bootstrap helper lives in alembic/migration_bootstrap.py (alongside env.py)
# so it's importable without an active Alembic context. Put the alembic dir on
# the path the same way Alembic itself does when it loads env.py.
_ALEMBIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic"
)
if _ALEMBIC_DIR not in sys.path:
    sys.path.insert(0, _ALEMBIC_DIR)

from migration_bootstrap import stamp_legacy_db_if_needed  # noqa: E402


def _alembic_version(connection) -> str | None:
    """Return the single stamped revision, or None if the table is absent."""
    inspector = sa.inspect(connection)
    if "alembic_version" not in inspector.get_table_names():
        return None
    row = connection.execute(
        sa.text("SELECT version_num FROM alembic_version")
    ).fetchone()
    return row[0] if row else None


@pytest.fixture
def conn():
    """A connection NOT inside an outer transaction — this mirrors how Alembic's
    env.py calls the helper (``connectable.connect()``), letting the helper open
    and commit its own transaction via ``connection.begin()``."""
    eng = create_engine("sqlite:///:memory:")
    with eng.connect() as connection:
        yield connection
    eng.dispose()


def _make_legacy_services_table(connection, *, with_external_host: bool) -> None:
    """Create a `services` table the way legacy create_all() left it — no
    alembic_version row. Optionally include the post-005 external_host column."""
    cols = [
        "id INTEGER PRIMARY KEY",
        "name VARCHAR(64) NOT NULL",
        "host VARCHAR(255) NOT NULL",
        "port INTEGER NOT NULL",
    ]
    if with_external_host:
        cols.append("external_host VARCHAR(255)")
        cols.append("external_port INTEGER")
    connection.execute(sa.text(f"CREATE TABLE services ({', '.join(cols)})"))


def test_stamps_004_when_services_predates_external_host(conn):
    """Legacy DB without external_host → baseline 004 (so migration 005 still runs)."""
    _make_legacy_services_table(conn, with_external_host=False)
    conn.commit()
    stamped = stamp_legacy_db_if_needed(conn)
    assert stamped == "004"
    assert _alembic_version(conn) == "004"


def test_stamps_005_when_services_has_external_host(conn):
    """Legacy DB already carrying external_host → baseline 005 (nothing left to run)."""
    _make_legacy_services_table(conn, with_external_host=True)
    conn.commit()
    stamped = stamp_legacy_db_if_needed(conn)
    assert stamped == "005"
    assert _alembic_version(conn) == "005"


def test_noop_on_fresh_empty_db(conn):
    """Truly empty DB (no services table) → no stamping; Alembic runs from 001."""
    stamped = stamp_legacy_db_if_needed(conn)
    assert stamped is None
    assert _alembic_version(conn) is None


def test_noop_when_already_stamped(conn):
    """Already-stamped DB → idempotent no-op, version left untouched."""
    _make_legacy_services_table(conn, with_external_host=True)
    conn.execute(
        sa.text(
            "CREATE TABLE alembic_version ("
            "version_num VARCHAR(32) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        )
    )
    conn.execute(
        sa.text("INSERT INTO alembic_version (version_num) VALUES ('003')")
    )
    conn.commit()
    stamped = stamp_legacy_db_if_needed(conn)
    assert stamped is None
    assert _alembic_version(conn) == "003"


def test_second_call_is_noop_after_stamping(conn):
    """Calling twice (e.g. restart) does not re-stamp or error."""
    _make_legacy_services_table(conn, with_external_host=False)
    conn.commit()
    assert stamp_legacy_db_if_needed(conn) == "004"
    # Second invocation now sees alembic_version present → no-op.
    assert stamp_legacy_db_if_needed(conn) is None
    assert _alembic_version(conn) == "004"

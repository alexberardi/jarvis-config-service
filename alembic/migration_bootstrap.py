"""One-time bootstrap to make `alembic upgrade head` safe on legacy DBs.

Incident (2026-06): config-service historically created its tables via
``Base.metadata.create_all()`` and never stamped an alembic baseline, so
existing/prod DBs have the tables but an EMPTY ``alembic_version``. The new
startup entrypoint runs a bare ``alembic upgrade head``, which on such a DB
would start from migration 001 and try to re-create the already-existing
``services`` table — crashing on startup.

This module's helper stamps such legacy DBs with the correct baseline so
Alembic only applies migrations the DB hasn't seen yet. It lives in its own
module (not in ``env.py``) so it can be imported and unit-tested without an
active Alembic context.
"""

import sqlalchemy as sa


def stamp_legacy_db_if_needed(connection) -> str | None:
    """Stamp a pre-Alembic config DB so `alembic upgrade head` is safe on it.

    If ``alembic_version`` is missing but ``services`` already exists (the
    legacy ``create_all()`` shape), create ``alembic_version`` and insert the
    correct baseline revision. Baseline is "005" if the ``services`` table
    already has the post-005 ``external_host`` column, else "004". This is a
    one-time no-op once stamped.

    Returns the baseline revision that was stamped, or ``None`` if no stamping
    was needed (already stamped, or a truly empty/fresh DB).
    """
    inspector = sa.inspect(connection)
    table_names = set(inspector.get_table_names())

    # Already stamped (or fresh DB with no tables) — nothing to do; let Alembic
    # run normally (creates everything from 001 on a truly empty DB). Reading
    # via the inspector autobegins a transaction on the connection; roll it back
    # so we hand Alembic a clean connection with no open transaction.
    if "alembic_version" in table_names or "services" not in table_names:
        connection.rollback()
        return None

    # Tables exist but no alembic_version → legacy create_all() DB. Pick the
    # baseline based on whether the post-005 column is already present.
    service_columns = {col["name"] for col in inspector.get_columns("services")}
    baseline = "005" if "external_host" in service_columns else "004"

    connection.execute(
        sa.text(
            "CREATE TABLE alembic_version ("
            "version_num VARCHAR(32) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        )
    )
    connection.execute(
        sa.text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
        {"rev": baseline},
    )
    # Commit the stamp explicitly so the baseline is durable even when Alembic
    # then has no pending migrations to run (an uncommitted INSERT would be lost
    # on the next `begin_transaction()`). Runs before Alembic opens its own
    # migration transaction, so this commit only finalizes the stamp.
    connection.commit()
    return baseline

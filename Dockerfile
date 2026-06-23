FROM python:3.11-slim

WORKDIR /app

# Install git (needed for pip git+https dependencies)
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Copy application
COPY app/ app/

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY alembic/ alembic/
COPY alembic.ini .

# Default port (can be overridden via JARVIS_CONFIG_PORT env var)
ENV JARVIS_CONFIG_PORT=7700

# Run alembic migrations BEFORE starting the app — same as every other Jarvis
# service (jarvis-auth et al. run `alembic upgrade head && <serve>`).
# config-service historically relied only on Base.metadata.create_all() in app
# startup, which CREATES missing tables but never ALTERs existing ones — so a new
# model column shipped via `docker compose pull` (e.g. services.external_host in
# migration 005) never reached the DB and every /services query 500'd until a
# human ran a migration by hand. Migrating on startup keeps schema and code in
# lockstep across all environments.
CMD ["/bin/sh", "-c", "python -m alembic upgrade head && python -m app.main"]

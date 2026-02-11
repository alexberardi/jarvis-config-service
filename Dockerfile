FROM python:3.11-slim

WORKDIR /app

# Install git (needed for pip git+https dependencies)
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --force-reinstall -r requirements.txt

# Copy application
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .

# Default port (can be overridden via JARVIS_CONFIG_PORT env var)
ENV JARVIS_CONFIG_PORT=8013

# Run using the app's main which reads port from env
CMD ["python", "-m", "app.main"]

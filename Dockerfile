FROM python:3.11-slim

WORKDIR /app

# Install git (needed for pip git+https dependencies)
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .

# Run
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8013"]

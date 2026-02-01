# Jarvis Config Service

Central service registry for the Jarvis ecosystem. Provides a single source of truth for service URLs, eliminating hardcoded endpoints across services.

## Why This Exists

Instead of every service having:
```bash
JARVIS_AUTH_URL=http://localhost:8007
JARVIS_LOGS_URL=http://localhost:8006
JARVIS_LLM_PROXY_URL=http://localhost:8003
# ... repeated across 12 services
```

Every service has ONE env var:
```bash
JARVIS_CONFIG_URL=http://pi-docker.local:8099
```

And fetches the rest at startup.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SERVICE STARTUP FLOW                             │
└─────────────────────────────────────────────────────────────────────────┘

1. Service starts
        │
        ▼
2. Read JARVIS_CONFIG_URL from env
        │
        ▼
3. GET /services → fetch all service URLs
        │
        ▼
4. Cache locally (DB or memory)
        │
        ▼
5. Service runs using cached URLs
        │
        ▼
6. (Optional) Periodic refresh in background
```

---

## API Endpoints

### Services

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| `GET` | `/services` | List all registered services | None |
| `GET` | `/services/{name}` | Get a specific service | None |
| `POST` | `/services` | Register a new service | Admin |
| `PUT` | `/services/{name}` | Update a service | Admin |
| `DELETE` | `/services/{name}` | Remove a service | Admin |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Config service health check |
| `GET` | `/services/{name}/health` | Proxy health check to a service |
| `GET` | `/services/health` | Health check all services |

---

## Data Model

```sql
CREATE TABLE services (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) UNIQUE NOT NULL,      -- e.g., "auth", "llm_proxy"
    host VARCHAR(255) NOT NULL,            -- e.g., "linux-workhorse.local"
    port INTEGER NOT NULL,                 -- e.g., 8003
    health_path VARCHAR(255) DEFAULT '/health',
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

## API Examples

### List all services
```bash
curl http://localhost:8013/services
```

Response:
```json
{
  "services": [
    {
      "name": "auth",
      "host": "pi-docker.local",
      "port": 8007,
      "url": "http://pi-docker.local:8007",
      "health_path": "/health"
    },
    {
      "name": "llm_proxy",
      "host": "linux-workhorse.local",
      "port": 8003,
      "url": "http://linux-workhorse.local:8003",
      "health_path": "/api/v1/health"
    }
  ]
}
```

### Get a specific service
```bash
curl http://localhost:8013/services/llm_proxy
```

Response:
```json
{
  "name": "llm_proxy",
  "host": "linux-workhorse.local",
  "port": 8003,
  "url": "http://linux-workhorse.local:8003",
  "health_path": "/api/v1/health"
}
```

### Register a new service (admin)
```bash
curl -X POST http://localhost:8013/services \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $JARVIS_CONFIG_ADMIN_TOKEN" \
  -d '{
    "name": "whisper",
    "host": "mac-mini.local",
    "port": 8004,
    "health_path": "/health",
    "description": "Speech-to-text service using CoreML Whisper"
  }'
```

### Update a service (admin)
```bash
curl -X PUT http://localhost:8013/services/llm_proxy \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $JARVIS_CONFIG_ADMIN_TOKEN" \
  -d '{
    "port": 8004
  }'
```

### Check health of all services
```bash
curl http://localhost:8013/services/health
```

Response:
```json
{
  "services": {
    "auth": {"healthy": true, "latency_ms": 12},
    "llm_proxy": {"healthy": true, "latency_ms": 45},
    "whisper": {"healthy": false, "error": "Connection refused"}
  },
  "healthy_count": 2,
  "total_count": 3
}
```

---

## Authentication

**Read endpoints are open** – any service on the network can discover other services.

**Write endpoints require admin token** – set via `JARVIS_CONFIG_ADMIN_TOKEN` env var. Passed in `X-Admin-Token` header.

This keeps it simple while preventing accidental misconfiguration.

---

## Client Usage

### Python (recommended)

Create a shared module or copy this pattern into services:

```python
# jarvis_config_client.py
import os
import httpx
from functools import lru_cache
from typing import Optional

CONFIG_URL = os.getenv("JARVIS_CONFIG_URL", "http://localhost:8013")

_service_cache: dict = {}

def fetch_services() -> dict:
    """Fetch all services from config service and cache them."""
    global _service_cache
    try:
        r = httpx.get(f"{CONFIG_URL}/services", timeout=5.0)
        r.raise_for_status()
        data = r.json()
        _service_cache = {s["name"]: s for s in data["services"]}
        return _service_cache
    except Exception as e:
        if _service_cache:
            # Return cached data if we have it
            print(f"Config service unavailable, using cache: {e}")
            return _service_cache
        raise RuntimeError(f"Cannot reach config service and no cache: {e}")

def get_service_url(name: str) -> str:
    """Get URL for a service by name."""
    if not _service_cache:
        fetch_services()
    if name not in _service_cache:
        raise KeyError(f"Unknown service: {name}")
    return _service_cache[name]["url"]

def get_service(name: str) -> dict:
    """Get full service config by name."""
    if not _service_cache:
        fetch_services()
    if name not in _service_cache:
        raise KeyError(f"Unknown service: {name}")
    return _service_cache[name]

# Optional: refresh cache periodically
async def start_background_refresh(interval_seconds: int = 60):
    """Start background task to refresh service cache."""
    import asyncio
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            fetch_services()
        except Exception as e:
            print(f"Background refresh failed: {e}")
```

### Usage in a service

```python
# At startup (e.g., in main.py or lifespan)
from jarvis_config_client import fetch_services, get_service_url

# Fetch and cache all services
fetch_services()

# Use throughout the app
auth_url = get_service_url("auth")
llm_url = get_service_url("llm_proxy")
```

### Store in database (optional)

If you want to persist to the service's local database:

```python
# At startup
from jarvis_config_client import fetch_services

def sync_services_to_db(db_session):
    """Fetch from config service and write to local settings table."""
    services = fetch_services()
    for name, config in services.items():
        db_session.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (:key, :value)
            ON CONFLICT (key) DO UPDATE SET value = :value
            """,
            {"key": f"service_url_{name}", "value": config["url"]}
        )
    db_session.commit()
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | - | Postgres connection string |
| `JARVIS_CONFIG_ADMIN_TOKEN` | Yes | - | Admin token for write operations |
| `PORT` | No | `8013` | Port to run on |

---

## Deployment

### Docker

```bash
docker build -t jarvis-config-service .
docker run -p 8013:8013 \
  -e DATABASE_URL=postgresql://user:pass@host:5432/jarvis_config \
  -e JARVIS_CONFIG_ADMIN_TOKEN=your-secret-token \
  jarvis-config-service
```

### Docker Compose

```yaml
services:
  jarvis-config:
    build: .
    ports:
      - "8013:8013"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/jarvis_config
      - JARVIS_CONFIG_ADMIN_TOKEN=${JARVIS_CONFIG_ADMIN_TOKEN}
    depends_on:
      - db

  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=jarvis_config
      - POSTGRES_PASSWORD=postgres
    volumes:
      - config_db_data:/var/lib/postgresql/data

volumes:
  config_db_data:
```

---

## Initial Service Registration

After deploying, register your services:

```bash
export CONFIG_URL=http://localhost:8013
export TOKEN=your-admin-token

# Auth service
curl -X POST $CONFIG_URL/services \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $TOKEN" \
  -d '{"name": "auth", "host": "pi-docker.local", "port": 8007}'

# LLM Proxy
curl -X POST $CONFIG_URL/services \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $TOKEN" \
  -d '{"name": "llm_proxy", "host": "linux-workhorse.local", "port": 8003, "health_path": "/api/v1/health"}'

# Command Center
curl -X POST $CONFIG_URL/services \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $TOKEN" \
  -d '{"name": "command_center", "host": "pi-docker.local", "port": 8002, "health_path": "/ping"}'

# Add more as needed
```

---

## Production Topology Example

```
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│    GPU SERVER       │    │     MAC MINI        │    │   DOCKER HOST       │
│                     │    │   (macOS-specific)  │    │                     │
├─────────────────────┤    ├─────────────────────┤    ├─────────────────────┤
│ • llm_proxy         │    │ • whisper           │    │ • config (8013) ◄───┼── Source of truth
│ • tts               │    │ • ocr               │    │ • auth              │
│                     │    │                     │    │ • command_center    │
│                     │    │                     │    │ • logs              │
│                     │    │                     │    │ • recipes           │
│                     │    │                     │    │ • mcp               │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
         │                          │                          │
         └──────────────────────────┴──────────────────────────┘
                    All services: JARVIS_CONFIG_URL=http://<config-host>:8013
```

---

## FAQ

**Q: What if the config service is down?**

A: Services cache the config at startup. If config service goes down, running services continue working. New services or restarts will fail until it's back.

**Q: Should I use this for secrets?**

A: No. This is for service discovery only. Use environment variables or a proper secrets manager for API keys, tokens, etc.

**Q: Can services register themselves?**

A: Could add that as a feature (service calls POST on startup), but for a small ecosystem with known services, manual registration is simpler and more predictable.

---

## Project Structure

```
jarvis-config-service/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, lifespan, CORS
│   ├── config.py            # Settings from env
│   ├── database.py          # DB connection
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py           # Pydantic schemas
│   └── routes/
│       ├── __init__.py
│       ├── services.py      # /services endpoints
│       └── health.py        # /health endpoints
├── alembic/
│   └── versions/
├── alembic.ini
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── run.sh
└── README.md
```

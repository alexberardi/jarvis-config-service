# jarvis-config-service

Central service registry for the Jarvis ecosystem. Provides a single source of truth for service URLs, eliminating hardcoded endpoints across services.

## Quick Reference

```bash
# Setup
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env and set DATABASE_URL and JARVIS_CONFIG_ADMIN_TOKEN

# Run migrations
.venv/bin/python -m alembic upgrade head

# Run (port 7700)
.venv/bin/uvicorn app.main:app --reload --port 7700

# Docker
docker-compose up --build

# Test
.venv/bin/pytest
```

## Architecture

```
app/
├── main.py              # FastAPI app, lifespan, CORS
├── config.py            # Settings from env
├── database.py          # DB connection
├── models.py            # SQLAlchemy models (Service)
├── schemas.py           # Pydantic schemas
└── routes/
    ├── services.py      # /services endpoints
    └── health.py        # /health endpoints
```

## Environment Variables

|| Variable | Required | Default | Description |
||----------|----------|---------|-------------|
|| `DATABASE_URL` | Yes | - | PostgreSQL connection string |
|| `JARVIS_CONFIG_ADMIN_TOKEN` | Yes | - | Admin token for write operations |
|| `PORT` | No | 7700 | Port to run on |

## API Endpoints

**Services:**
- `GET /services` → List all registered services
- `GET /services/{name}` → Get a specific service
- `POST /services` → Register a new service (admin)
- `PUT /services/{name}` → Update a service (admin)
- `DELETE /services/{name}` → Remove a service (admin)

**Health:**
- `GET /health` → Config service health check
- `GET /services/{name}/health` → Proxy health check to a service
- `GET /services/health` → Health check all services

**Info:**
- `GET /info` → Service info (for discovery)

## Authentication

**Read endpoints are open** – any service on the network can discover other services.

**Write endpoints require admin token** – set via `JARVIS_CONFIG_ADMIN_TOKEN` env var. Passed in `X-Admin-Token` header.

## Service Discovery Flow

```
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

## Dependencies

**Python Libraries:**
- FastAPI, SQLAlchemy, Alembic
- psycopg2 (PostgreSQL driver)
- httpx (health check proxying)

**Service Dependencies:**
- ✅ **Required**: PostgreSQL - Database for service registry
- ⚠️ **Optional**: None (this is the foundation service)

**Used By:**
- ALL jarvis services - Service URL discovery
- `jarvis-admin` - Network discovery to find config service
- `jarvis-mcp` - Service discovery for Claude Code tools
- `jarvis-settings-server` - Service discovery for settings aggregation

**Impact if Down:**
- ❌ New services cannot start (no service discovery)
- ❌ Services cannot refresh their service URL cache
- ✅ Running services continue with cached URLs
- ✅ Services with env var fallbacks continue

## Client Usage Pattern

Services typically use this pattern:

```python
import os
import httpx

CONFIG_URL = os.getenv("JARVIS_CONFIG_URL", "http://localhost:7700")
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
            return _service_cache
        raise RuntimeError(f"Cannot reach config service and no cache: {e}")

def get_service_url(name: str) -> str:
    """Get URL for a service by name."""
    if not _service_cache:
        fetch_services()
    return _service_cache[name]["url"]
```

## Initial Service Registration

After deploying, register your services:

```bash
export CONFIG_URL=http://localhost:7700
export TOKEN=your-admin-token

# Auth service
curl -X POST $CONFIG_URL/services \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $TOKEN" \
  -d '{"name": "jarvis-auth", "host": "localhost", "port": 7701}'

# LLM Proxy
curl -X POST $CONFIG_URL/services \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $TOKEN" \
  -d '{"name": "jarvis-llm-proxy-api", "host": "localhost", "port": 7704}'

# Add more as needed
```

## Database

PostgreSQL is required. The service stores:

```sql
CREATE TABLE services (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) UNIQUE NOT NULL,      -- e.g., "jarvis-auth"
    host VARCHAR(255) NOT NULL,            -- e.g., "localhost"
    port INTEGER NOT NULL,                 -- e.g., 7701
    health_path VARCHAR(255) DEFAULT '/health',
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

## Why This Exists

Instead of every service having:
```bash
JARVIS_AUTH_URL=http://localhost:7701
JARVIS_LOGS_URL=http://localhost:7702
JARVIS_LLM_PROXY_URL=http://localhost:7704
# ... repeated across 12+ services
```

Every service has ONE env var:
```bash
JARVIS_CONFIG_URL=http://localhost:7700
```

And fetches the rest at startup.

# jarvis-config-service

The foundation service. Every other Jarvis service depends on this one for URL discovery. Also acts as the **bootstrap controller** (first-boot service + auth-credential provisioning) and a **settings gateway** for admin tooling.

> **Identity rule:** if you're tempted to add a "JARVIS_X_URL" env var to any service, stop. URLs come from config-service. The only env var a consumer should need is `JARVIS_CONFIG_URL`.

---

## What this service is (and isn't)

| Responsibility | Endpoint prefix | Auth |
|---|---|---|
| **Service registry** — URLs of all services, queried at startup by everyone | `/services` (read open, writes admin) | open read / admin write |
| **Bootstrap controller** — first-boot bulk registration that also creates app-credentials in `jarvis-auth` and writes `.env` files | `/v1/services` | admin token OR superuser JWT |
| **Settings gateway** — fan-out aggregator that pulls `/settings/` from every registered service for the admin UI | `/v1/settings` | superuser JWT |
| **Its own settings** — config-service has its own settings table too (uses the standard `jarvis-settings-client` mount) | `/settings` | superuser JWT |

**Not** a:
- Persistent settings store for other services — each service owns its own settings; this aggregates them.
- Health monitor — `/services/health` exists but is on-demand, not a heartbeat system.

---

## Quick Reference

```bash
# Local dev (port 7700)
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env  # set DATABASE_URL + JARVIS_CONFIG_ADMIN_TOKEN at minimum
.venv/bin/python -m alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 7700

# Docker
docker-compose up --build

# Test (unit tests only — integration tests pending)
.venv/bin/pytest
```

---

## Dependency graph

**Upstream (config-service depends on):**
- **PostgreSQL** (required) — registry + settings tables
- **jarvis-auth** (required for `/v1/services/*` bootstrap and `/v1/settings/*` JWT validation) — uses admin token to manage app-clients, uses public key/secret to validate superuser JWTs
- **jarvis-settings-client** (library) — provides `create_superuser_auth()` and the `/settings` router that this service mounts for its own settings

**Downstream (depends on config-service):**
- **All** Jarvis services — read `/services` at startup via `jarvis-config-client`
- **jarvis-admin** — uses `/v1/settings/*` to read/write user settings across the stack
- **jarvis CLI / installer** — uses `/v1/services/register` for first-boot bootstrap
- **jarvis-mcp** — service discovery for debugging tools

**Impact if down:**
- Running services keep working — `jarvis-config-client` caches URLs in-process and (optionally) in a DB
- New services can't start — they need to fetch service URLs on boot
- No new service registration possible
- Admin UI loses ability to manage settings across services

---

## Lifecycle / common operations

### 1. Service discovery (the hot path, called by every service on startup)

```
Service starts
  → reads JARVIS_CONFIG_URL env var
  → jarvis_config_client.init(config_url=...) at FastAPI startup
  → client GETs /services and caches the result
  → service code calls get_service_url("jarvis-auth"), etc.
```

**See `jarvis-config-client/CLAUDE.md` for client caching/refresh behavior.** Don't hand-roll an httpx fetch — use the client.

Files touched on this path: `app/routes/services.py:list_services` → DB query → response. No auth required.

### 2. First-boot bootstrap (called by jarvis CLI / installer)

```
POST /v1/services/register
  body: {"services": [{name, host, port, scheme, ...}], "base_path": "/path/to/jarvis"}
  auth: X-Jarvis-Admin-Token OR superuser JWT
```

For each service in the batch, `service_registration.py:_register_one`:
1. **Upserts** in config DB `services` table
2. **POSTs to `jarvis-auth /admin/app-clients`** to create the app credential (idempotent — skips if app_id already exists)
3. **Writes `JARVIS_APP_ID` + `JARVIS_APP_KEY` to `<base_path>/<service_name>/.env`** (preserves other env keys; only overwrites these two)

Why two-step auth (admin token OR JWT): the admin token path exists because at first-boot there are no users yet, so no JWTs can be minted. After the first superuser exists, JWT is preferred.

Companion endpoints (same auth):
- `GET /v1/services/registry` — known services + their registration status (config DB + auth) — used by admin UI to show what still needs setup
- `POST /v1/services/rotate-key` — rotate an app's key in auth + rewrite its `.env`
- `POST /v1/services/probe` — health probe an arbitrary host:port (used by admin "test connection" buttons)
- `DELETE /v1/services/{name}` — only allowed for **custom** services; KNOWN_SERVICES entries are protected

### 3. Settings aggregation (admin UI reads everyone's settings)

```
GET /v1/settings           → fans out to every registered service's /settings/
GET /v1/settings?service=X → fan out to one service only
PUT /v1/settings/{service}/{key}  → proxies the write to that service's /settings/{key}
```

Auth: superuser JWT. The gateway forwards both the JWT **and** config-service's own app-to-app credentials when calling downstream services.

A service is excluded from the aggregated response if it returns 404 on `/settings/` (i.e. it doesn't have a settings router). Errors are surfaced per-service in the response, not aggregated into a single failure.

### 4. URL style negotiation (Docker / remote callers)

`GET /services?style=dockerized` returns URLs with `localhost`→`host.docker.internal`. `style=remote&remote_host=<gpu-host>` rewrites to a specific IP. This is **per-request**, not a service-wide setting — the *caller* decides what style it needs.

Used by: dockerized services on macOS (where GPU services run on the host), `jarvis-node-mobile` connecting from a different host.

---

## "How to..." recipes

### Add a new Jarvis service to the ecosystem

1. **Add to `app/known_services.py`** with default port, description, health_path. Names must match the service directory name (`jarvis-foo`, not `foo`). This makes it appear in the admin "services to set up" list and gives it sensible defaults.
2. The first-boot bulk-register flow (or the admin UI) will pick it up automatically — no other config-service changes needed.
3. In the new service's code, use `jarvis-config-client` to discover other service URLs. Do **not** add `JARVIS_X_URL` env vars (see Invariants).

> "Custom" services (not in `known_services.py`) can still be registered via `/v1/services/register` and used; they just won't appear in the admin "expected services" list and can be deleted via `DELETE /v1/services/{name}`.

### Add a new admin-token-protected endpoint

- For simple CRUD on the registry: add to `app/routes/services.py`, depend on `require_admin` from `app/auth.py`.
- For anything that touches `jarvis-auth` (creating app-clients, rotating keys): add to `app/routes/service_registration.py`, use the `either_auth` dependency (admin token OR superuser JWT) so the installer can call it before any user exists.

### Add a new style of URL rewriting (e.g. an IPv6 mode)

`app/routes/services.py:UrlStyle` (enum), `_resolve_url_params`, and `Service.get_url` in `app/models.py`. The enum is exposed as a query param across `/services` and `/services/{name}`.

---

## Invariants & gotchas

1. **No env URL fallbacks.** Services should fail loud if they can't reach config-service. Do not paper over with `JARVIS_X_URL` defaults — it masks real configuration problems and creates drift between environments. Only `JARVIS_CONFIG_URL` itself is an env var.
2. **`known_services.py` is defaults-only, not authoritative.** The DB is the source of truth at runtime. `known_services.py` provides (a) defaults during bootstrap, (b) the "expected services" list for admin UX, (c) the "protected from deletion" set. **You may add to it freely.** Adding new entries is well-supported; arbitrary custom services (not in this list) are supported but less battle-tested.
3. **Bootstrap dual-auth is intentional.** `X-Jarvis-Admin-Token` (config-service's `JARVIS_CONFIG_ADMIN_TOKEN`) is a shared secret used during first-boot. Once a superuser exists, prefer JWT. Don't remove the admin-token path — it's the chicken-and-egg solution.
4. **`JARVIS_AUTH_ADMIN_TOKEN` is different from `JARVIS_CONFIG_ADMIN_TOKEN`.** The former is what config-service uses to call `jarvis-auth /admin/*`. The latter is what callers use to authenticate to config-service. Don't conflate.
5. **`JARVIS_CONFIG_URL_STYLE` is a request-time concern, not a runtime config.** Callers pass `?style=dockerized` per request. There's no global server-side switch. (The env var `DOCKER_HOST_GATEWAY` only affects *outbound* probes / settings fan-outs originating from config-service itself.)
6. **`/info` is intentionally unauthenticated** — used for network discovery (e.g. `jarvis-admin` scanning the LAN to find the config service). Don't add auth to it.
7. **`jarvis_settings_client.create_superuser_auth` is created at module import time** in `main.py`, then passed into router factories. Tests override it via FastAPI's dependency_overrides. Don't try to construct routers without the factory.
8. **The settings gateway here is the canonical settings aggregator.** `jarvis-settings-server` (port 7708) exposes the same surface but **nothing routes to it** — admin calls this gateway at `${configUrl}/v1/settings/*` directly (see `jarvis-admin/server/src/routes/settings.ts`, `quick-sets.ts`, `llm-setup.ts`). Treat `jarvis-settings-server` as the deprecation candidate. If you need to extend settings aggregation, do it here.

---

## Data model

**Two tables**, both managed by Alembic (`alembic/versions/`):

```python
# Service registry — the heart of discovery
class Service:
    id: int
    name: str               # UNIQUE — e.g. "jarvis-auth"; matches directory/CLI name
    host: str               # "localhost", "host.docker.internal", IPs, hostnames
    port: int
    scheme: str             # http | https | mqtt | mqtts | ws | wss
    health_path: str        # default "/health"
    description: str | None
    created_at, updated_at

# Settings — multi-tenant scoped
class Setting:
    id: int
    key: str                # e.g. "voice.wake_word"
    value: str | None       # JSON-encoded
    value_type: str         # "string" | "int" | "bool" | "json"
    category: str           # "general", grouping for UI
    description: str | None
    requires_reload: bool   # whether the owning service needs a restart after change
    is_secret: bool         # hide value in API responses
    env_fallback: str | None  # env var to read if no DB value

    # Multi-tenant scoping — all NULLABLE; NULL = system default
    household_id: str | None
    node_id: str | None
    user_id: int | None

    # UNIQUE(key, household_id, node_id, user_id)
```

The settings table here only holds **config-service's own settings**. Other services have their own `settings` tables. The gateway proxies between them — it never reads/writes this DB on behalf of other services.

---

## Config surface

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | yes | `postgresql://postgres:postgres@localhost:5432/jarvis_config` | Runtime DB connection |
| `MIGRATIONS_DATABASE_URL` | no | same as above | Used by Alembic; sometimes differs from runtime when running migrations from the host while the app runs in Docker |
| `JARVIS_CONFIG_ADMIN_TOKEN` | yes for writes | empty | Admin token clients send as `X-Admin-Token` (legacy `/services` CRUD) or `X-Jarvis-Admin-Token` (`/v1/services/*` bootstrap) |
| `JARVIS_AUTH_URL` | yes | `http://localhost:7701` | Where to find jarvis-auth (used during bootstrap and JWT validation) |
| `JARVIS_AUTH_ADMIN_TOKEN` | yes for bootstrap | empty | Admin token config-service uses when calling jarvis-auth `/admin/app-clients` |
| `JARVIS_APP_ID` | for settings gateway | empty | This service's own app-credential for app-to-app calls (typically `jarvis-config-service`) |
| `JARVIS_APP_KEY` | for settings gateway | empty | App credential key paired with the above |
| `SETTINGS_GATEWAY_TIMEOUT` | no | `10.0` | Per-service fan-out timeout (seconds) |
| `HEALTH_CHECK_TIMEOUT` | no | `5.0` | Timeout for `/services/health` probes |
| `DOCKER_HOST_GATEWAY` | macOS Docker | empty | Set to `host.docker.internal` so probes / outbound settings calls reach the host. **This is for outbound only**; URL style for inbound requests is per-request. |
| `JARVIS_REMOTE_HOST` | optional | empty | Fallback host for `?style=remote` if no `remote_host` query param |
| `JARVIS_ROOT` | bootstrap | empty | Path to the jarvis directory tree inside the container, used to write `.env` files during registration. Mounted via volume in docker-compose. |
| `JARVIS_CONFIG_PORT` / `PORT` | no | `7700` | HTTP port |
| `HOST` | no | `0.0.0.0` | Bind address |

---

## Architecture

```
app/
├── main.py                          # FastAPI app, lifespan, router wiring
├── config.py                        # Settings via env (see above)
├── database.py                      # SQLAlchemy engine + Base
├── models.py                        # Service, Setting (multi-tenant)
├── schemas.py                       # Pydantic — request/response shapes
├── auth.py                          # require_admin dependency (X-Admin-Token)
├── known_services.py                # Static defaults + "expected" list
├── routes/
│   ├── services.py                  # /services CRUD + /services/health + URL style negotiation
│   ├── service_registration.py      # /v1/services/* bootstrap, auth-credential provisioning, .env writes
│   └── settings_gateway.py          # /v1/settings/* fan-out aggregator
└── services/
    └── settings_service.py          # Backing store for config-service's own /settings

alembic/                             # Migrations for services + settings tables
tests/                               # Unit tests (no integration tests yet)
```

---

## Testing

- **Unit tests only today.** Integration tests are deliberately not in place yet — environmental constraints (no in-CI Postgres) made it infeasible. This is on the roadmap and will be required before the automated-coding workflow ships.
- DB is **mocked** via a test-scoped SQLite engine in `tests/conftest.py`. The schema is created via `Base.metadata.create_all`, not Alembic, in tests.
- Auth dependencies are overridden via FastAPI's `dependency_overrides` — see `tests/helpers.py`.
- When adding a new route: write a unit test that hits it through the TestClient and asserts on the response shape. Stub any outbound httpx calls with `respx` or monkey-patched mocks; don't hit real services.

Run: `.venv/bin/pytest` (no [dev] extras needed beyond `pytest` itself).

---

## Failure modes

| Failure | Behavior |
|---|---|
| Postgres down | Config-service won't start; cascade failure across the stack on next deploy |
| `jarvis-auth` down during `/v1/services/register` | Config DB row is still upserted, but `auth_ok=False` in the response per service; can be retried |
| `jarvis-auth` down during settings gateway request | Superuser JWT validation fails → 401; admin UI degrades |
| `JARVIS_AUTH_ADMIN_TOKEN` unset | `/v1/services/register` returns 500; `/v1/services/registry` returns entries with `auth_registered=False` |
| Service in DB but unreachable | `/v1/settings` aggregation returns a per-service `success=False` with the connection error; other services still aggregate normally |
| Wrong `style` query param | 422 Unprocessable Entity (Pydantic enum validation) |

---

## Out of scope / explicitly not here

- **Heartbeat / liveness monitoring.** This service offers on-demand health checks but doesn't continuously monitor. If you want continuous monitoring, that belongs elsewhere.
- **Service auto-registration on boot.** Services don't self-register here; the installer / `jarvis CLI` does bulk registration. (Auto-registration was considered and rejected — it makes order-of-boot fragile.)
- **Client-side caching.** Caching, refresh, and DB persistence live in `jarvis-config-client`, not here. This service is stateless except for the DB.
- **Cross-service settings.** A setting like "wake_word" is owned by the service that uses it. The gateway proxies; it doesn't own.

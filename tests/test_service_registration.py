"""Tests for service registration endpoints."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

# Ensure env is set before app imports
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JARVIS_CONFIG_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("JARVIS_AUTH_URL", "http://localhost:8007")
os.environ.setdefault("JARVIS_AUTH_ADMIN_TOKEN", "test-auth-admin-token")

from app.known_services import KNOWN_SERVICES
from app.models import Service


def _mock_async_client(
    get_response=None,
    post_response=None,
    get_side_effect=None,
    post_side_effect=None,
):
    """Create a mock httpx.AsyncClient context manager.

    Returns (patcher, mock_instance) where mock_instance has .get and .post.
    """
    mock_instance = AsyncMock()

    if get_side_effect:
        mock_instance.get.side_effect = get_side_effect
    elif get_response is not None:
        mock_instance.get.return_value = get_response

    if post_side_effect:
        mock_instance.post.side_effect = post_side_effect
    elif post_response is not None:
        mock_instance.post.return_value = post_response

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    patcher = patch(
        "app.routes.service_registration.httpx.AsyncClient",
        return_value=mock_ctx,
    )
    return patcher, mock_instance


# ── GET /v1/services/registry ──


class TestGetServiceRegistry:
    """Tests for GET /v1/services/registry."""

    def test_returns_all_known_services(self, client):
        """Registry returns every known service with default status."""
        patcher, _ = _mock_async_client(
            get_response=httpx.Response(200, json=[]),
        )
        with patcher:
            resp = client.get("/v1/services/registry")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["services"]) == len(KNOWN_SERVICES)
        names = {s["name"] for s in data["services"]}
        for ks in KNOWN_SERVICES:
            assert ks["name"] in names

    def test_shows_config_registered_when_in_db(self, client, db_session):
        """Services in the config DB show config_registered=True."""
        svc = Service(
            name="jarvis-logs", host="localhost", port=8006,
            scheme="http", health_path="/health", description="Logging",
        )
        db_session.add(svc)
        db_session.commit()

        patcher, _ = _mock_async_client(
            get_response=httpx.Response(200, json=[]),
        )
        with patcher:
            resp = client.get("/v1/services/registry")

        data = resp.json()
        logs_entry = next(s for s in data["services"] if s["name"] == "jarvis-logs")
        assert logs_entry["config_registered"] is True
        assert logs_entry["current_host"] == "localhost"
        assert logs_entry["current_port"] == 8006

        auth_entry = next(s for s in data["services"] if s["name"] == "jarvis-auth")
        assert auth_entry["config_registered"] is False
        assert auth_entry["current_host"] is None

    def test_shows_auth_registered_when_in_auth(self, client):
        """Services with an app-client in jarvis-auth show auth_registered=True."""
        auth_clients = [
            {"app_id": "jarvis-logs", "name": "jarvis-logs", "is_active": True},
            {"app_id": "jarvis-auth", "name": "jarvis-auth", "is_active": True},
        ]

        patcher, _ = _mock_async_client(
            get_response=httpx.Response(200, json=auth_clients),
        )
        with patcher:
            resp = client.get("/v1/services/registry")

        data = resp.json()
        logs_entry = next(s for s in data["services"] if s["name"] == "jarvis-logs")
        assert logs_entry["auth_registered"] is True

        tts_entry = next(s for s in data["services"] if s["name"] == "jarvis-tts")
        assert tts_entry["auth_registered"] is False

    def test_auth_service_unreachable_still_returns(self, client):
        """Registry still returns results when jarvis-auth is unreachable."""
        patcher, _ = _mock_async_client(
            get_side_effect=httpx.ConnectError("Connection refused"),
        )
        with patcher:
            resp = client.get("/v1/services/registry")

        assert resp.status_code == 200
        data = resp.json()
        for svc in data["services"]:
            assert svc["auth_registered"] is False


# ── POST /v1/services/register ──


class TestRegisterServices:
    """Tests for POST /v1/services/register."""

    def test_register_creates_config_and_auth(self, client, db_session):
        """Registering a new service creates config DB row and auth app-client."""
        patcher, mock_inst = _mock_async_client(
            get_response=httpx.Response(200, json=[]),
            post_response=httpx.Response(
                201, json={"app_id": "jarvis-logs", "key": "secret-key-123"},
            ),
        )
        with patcher:
            resp = client.post(
                "/v1/services/register",
                json={"services": [{"name": "jarvis-logs", "host": "localhost", "port": 8006}]},
            )

        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["name"] == "jarvis-logs"
        assert results[0]["config_ok"] is True
        assert results[0]["auth_ok"] is True
        assert results[0]["auth_created"] is True
        assert results[0]["app_key"] == "secret-key-123"

        # Verify config DB entry
        svc = db_session.query(Service).filter(Service.name == "jarvis-logs").first()
        assert svc is not None
        assert svc.port == 8006

    def test_register_updates_existing_config(self, client, db_session):
        """Re-registering a service updates the config DB row."""
        svc = Service(
            name="jarvis-logs", host="localhost", port=8006,
            scheme="http", health_path="/health",
        )
        db_session.add(svc)
        db_session.commit()

        patcher, _ = _mock_async_client(
            get_response=httpx.Response(
                200, json=[{"app_id": "jarvis-logs"}],
            ),
        )
        with patcher:
            resp = client.post(
                "/v1/services/register",
                json={"services": [{"name": "jarvis-logs", "host": "192.168.1.50", "port": 9006}]},
            )

        assert resp.status_code == 200
        results = resp.json()["results"]
        assert results[0]["config_ok"] is True
        assert results[0]["auth_ok"] is True
        assert results[0]["auth_created"] is False
        assert results[0]["app_key"] is None

        # Verify updated
        db_session.expire_all()
        svc = db_session.query(Service).filter(Service.name == "jarvis-logs").first()
        assert svc.host == "192.168.1.50"
        assert svc.port == 9006

    def test_register_skips_auth_if_already_exists(self, client, db_session):
        """If app-client already exists in jarvis-auth, skip creation."""
        patcher, mock_inst = _mock_async_client(
            get_response=httpx.Response(
                200, json=[{"app_id": "jarvis-tts"}],
            ),
        )
        with patcher:
            resp = client.post(
                "/v1/services/register",
                json={"services": [{"name": "jarvis-tts", "host": "localhost", "port": 8009}]},
            )

        assert resp.status_code == 200
        results = resp.json()["results"]
        assert results[0]["auth_ok"] is True
        assert results[0]["auth_created"] is False
        assert results[0]["app_key"] is None
        # post should NOT have been called
        mock_inst.post.assert_not_called()

    def test_register_multiple_services(self, client, db_session):
        """Can register multiple services in one request."""
        patcher, _ = _mock_async_client(
            get_response=httpx.Response(200, json=[]),
            post_response=httpx.Response(
                201, json={"app_id": "test", "key": "k"},
            ),
        )
        with patcher:
            resp = client.post(
                "/v1/services/register",
                json={
                    "services": [
                        {"name": "jarvis-logs", "host": "localhost", "port": 8006},
                        {"name": "jarvis-tts", "host": "localhost", "port": 8009},
                    ]
                },
            )

        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 2
        assert all(r["config_ok"] for r in results)

    def test_register_auth_service_down(self, client, db_session):
        """Config DB succeeds even if jarvis-auth is unreachable."""
        patcher, _ = _mock_async_client(
            get_side_effect=httpx.ConnectError("Connection refused"),
        )
        with patcher:
            resp = client.post(
                "/v1/services/register",
                json={"services": [{"name": "jarvis-logs", "host": "localhost", "port": 8006}]},
            )

        assert resp.status_code == 200
        results = resp.json()["results"]
        assert results[0]["config_ok"] is True
        assert results[0]["auth_ok"] is False
        assert results[0]["error"] is not None

        # Config DB entry still created
        svc = db_session.query(Service).filter(Service.name == "jarvis-logs").first()
        assert svc is not None

    def test_register_no_admin_token_configured(self, client):
        """Returns 500 if JARVIS_AUTH_ADMIN_TOKEN is not configured."""
        with patch("app.routes.service_registration.get_settings") as mock_settings:
            mock_settings.return_value.JARVIS_AUTH_ADMIN_TOKEN = ""

            resp = client.post(
                "/v1/services/register",
                json={"services": [{"name": "jarvis-logs", "host": "localhost", "port": 8006}]},
            )

        assert resp.status_code == 500
        assert "JARVIS_AUTH_ADMIN_TOKEN" in resp.json()["detail"]


# ── .env file writing ──


class TestEnvFileWriting:
    """Tests for .env file writing via base_path."""

    def test_writes_env_file_for_new_service(self, client, db_session, tmp_path):
        """When base_path is set and auth creates a key, writes .env file."""
        patcher, _ = _mock_async_client(
            get_response=httpx.Response(200, json=[]),
            post_response=httpx.Response(
                201, json={"app_id": "jarvis-logs", "key": "new-secret-key"},
            ),
        )
        with patcher:
            resp = client.post(
                "/v1/services/register",
                json={
                    "services": [{"name": "jarvis-logs", "host": "localhost", "port": 8006}],
                    "base_path": str(tmp_path),
                },
            )

        assert resp.status_code == 200
        results = resp.json()["results"]
        assert results[0]["env_written"] is True

        env_file = tmp_path / "jarvis-logs" / ".env"
        assert env_file.exists()
        content = env_file.read_text()
        assert "JARVIS_APP_ID=jarvis-logs" in content
        assert "JARVIS_APP_KEY=new-secret-key" in content

    def test_appends_to_existing_env_file(self, client, db_session, tmp_path):
        """When .env already exists, appends new vars without overwriting."""
        service_dir = tmp_path / "jarvis-tts"
        service_dir.mkdir()
        env_file = service_dir / ".env"
        env_file.write_text("DATABASE_URL=sqlite:///test.db\nPORT=8009\n")

        patcher, _ = _mock_async_client(
            get_response=httpx.Response(200, json=[]),
            post_response=httpx.Response(
                201, json={"app_id": "jarvis-tts", "key": "tts-key"},
            ),
        )
        with patcher:
            resp = client.post(
                "/v1/services/register",
                json={
                    "services": [{"name": "jarvis-tts", "host": "localhost", "port": 8009}],
                    "base_path": str(tmp_path),
                },
            )

        results = resp.json()["results"]
        assert results[0]["env_written"] is True

        content = env_file.read_text()
        assert "DATABASE_URL=sqlite:///test.db" in content
        assert "PORT=8009" in content
        assert "JARVIS_APP_ID=jarvis-tts" in content
        assert "JARVIS_APP_KEY=tts-key" in content

    def test_updates_existing_env_vars_in_place(self, client, db_session, tmp_path):
        """When .env already has JARVIS_APP_ID/KEY, updates them in place."""
        service_dir = tmp_path / "jarvis-logs"
        service_dir.mkdir()
        env_file = service_dir / ".env"
        env_file.write_text(
            "DATABASE_URL=sqlite:///test.db\n"
            "JARVIS_APP_ID=old-id\n"
            "JARVIS_APP_KEY=old-key\n"
            "PORT=8006\n"
        )

        patcher, _ = _mock_async_client(
            get_response=httpx.Response(200, json=[]),
            post_response=httpx.Response(
                201, json={"app_id": "jarvis-logs", "key": "new-key"},
            ),
        )
        with patcher:
            resp = client.post(
                "/v1/services/register",
                json={
                    "services": [{"name": "jarvis-logs", "host": "localhost", "port": 8006}],
                    "base_path": str(tmp_path),
                },
            )

        results = resp.json()["results"]
        assert results[0]["env_written"] is True

        content = env_file.read_text()
        assert "JARVIS_APP_ID=jarvis-logs" in content
        assert "JARVIS_APP_KEY=new-key" in content
        assert "old-id" not in content
        assert "old-key" not in content
        assert "DATABASE_URL=sqlite:///test.db" in content
        assert "PORT=8006" in content

    def test_no_env_written_without_base_path(self, client, db_session):
        """Without base_path, env_written is null."""
        patcher, _ = _mock_async_client(
            get_response=httpx.Response(200, json=[]),
            post_response=httpx.Response(
                201, json={"app_id": "jarvis-logs", "key": "key"},
            ),
        )
        with patcher:
            resp = client.post(
                "/v1/services/register",
                json={"services": [{"name": "jarvis-logs", "host": "localhost", "port": 8006}]},
            )

        results = resp.json()["results"]
        assert results[0]["env_written"] is None

    def test_no_env_written_when_auth_already_exists(self, client, db_session, tmp_path):
        """When auth already exists (no new key), no .env write happens."""
        patcher, _ = _mock_async_client(
            get_response=httpx.Response(
                200, json=[{"app_id": "jarvis-logs"}],
            ),
        )
        with patcher:
            resp = client.post(
                "/v1/services/register",
                json={
                    "services": [{"name": "jarvis-logs", "host": "localhost", "port": 8006}],
                    "base_path": str(tmp_path),
                },
            )

        results = resp.json()["results"]
        # No new key was created, so no .env write
        assert results[0]["env_written"] is None

        env_file = tmp_path / "jarvis-logs" / ".env"
        assert not env_file.exists()


# ── POST /v1/services/rotate-key ──


class TestRotateKey:
    """Tests for POST /v1/services/rotate-key."""

    def test_rotate_key_returns_new_key(self, client):
        """Rotating a key returns the new app key."""
        patcher, mock_inst = _mock_async_client(
            post_response=httpx.Response(
                200, json={"app_id": "jarvis-logs", "key": "rotated-key-456"},
            ),
        )
        with patcher:
            resp = client.post(
                "/v1/services/rotate-key",
                json={"service_name": "jarvis-logs"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["service_name"] == "jarvis-logs"
        assert data["app_key"] == "rotated-key-456"
        assert data["env_written"] is None

    def test_rotate_key_writes_env(self, client, tmp_path):
        """Rotating with base_path writes the new key to .env."""
        service_dir = tmp_path / "jarvis-logs"
        service_dir.mkdir()
        env_file = service_dir / ".env"
        env_file.write_text("JARVIS_APP_ID=jarvis-logs\nJARVIS_APP_KEY=old-key\n")

        patcher, _ = _mock_async_client(
            post_response=httpx.Response(
                200, json={"app_id": "jarvis-logs", "key": "rotated-key"},
            ),
        )
        with patcher:
            resp = client.post(
                "/v1/services/rotate-key",
                json={"service_name": "jarvis-logs", "base_path": str(tmp_path)},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["app_key"] == "rotated-key"
        assert data["env_written"] is True

        content = env_file.read_text()
        assert "JARVIS_APP_KEY=rotated-key" in content
        assert "old-key" not in content

    def test_rotate_key_auth_service_down(self, client):
        """Returns 502 when jarvis-auth is unreachable."""
        patcher, _ = _mock_async_client(
            post_side_effect=httpx.ConnectError("Connection refused"),
        )
        with patcher:
            resp = client.post(
                "/v1/services/rotate-key",
                json={"service_name": "jarvis-logs"},
            )

        assert resp.status_code == 502

    def test_rotate_key_auth_returns_error(self, client):
        """Returns auth's error status when rotate fails."""
        patcher, _ = _mock_async_client(
            post_response=httpx.Response(404, text="Not found"),
        )
        with patcher:
            resp = client.post(
                "/v1/services/rotate-key",
                json={"service_name": "nonexistent-service"},
            )

        assert resp.status_code == 404


# ── POST /v1/services/probe ──


class TestProbeHealth:
    """Tests for POST /v1/services/probe."""

    def test_probe_healthy_service(self, client):
        """Returns healthy=True with latency when endpoint responds 200."""
        patcher, mock_inst = _mock_async_client(
            get_response=httpx.Response(200, json={"status": "ok"}),
        )
        with patcher:
            resp = client.post(
                "/v1/services/probe",
                json={"host": "localhost", "port": 8006},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] is True
        assert data["latency_ms"] is not None
        assert data["error"] is None

    def test_probe_unhealthy_service(self, client):
        """Returns healthy=False when endpoint responds non-200."""
        patcher, _ = _mock_async_client(
            get_response=httpx.Response(503, text="Service Unavailable"),
        )
        with patcher:
            resp = client.post(
                "/v1/services/probe",
                json={"host": "localhost", "port": 8006},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] is False
        assert data["error"] == "HTTP 503"
        assert data["latency_ms"] is not None

    def test_probe_connection_refused(self, client):
        """Returns healthy=False when service is unreachable."""
        patcher, _ = _mock_async_client(
            get_side_effect=httpx.ConnectError("Connection refused"),
        )
        with patcher:
            resp = client.post(
                "/v1/services/probe",
                json={"host": "localhost", "port": 9999},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] is False
        assert data["error"] == "Connection refused"
        assert data["latency_ms"] is None

    def test_probe_timeout(self, client):
        """Returns healthy=False when service times out."""
        patcher, _ = _mock_async_client(
            get_side_effect=httpx.TimeoutException("Timed out"),
        )
        with patcher:
            resp = client.post(
                "/v1/services/probe",
                json={"host": "localhost", "port": 8006},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] is False
        assert data["error"] == "Timeout"

    def test_probe_custom_health_path_and_scheme(self, client):
        """Respects custom health_path and scheme parameters."""
        patcher, mock_inst = _mock_async_client(
            get_response=httpx.Response(200, json={"status": "ok"}),
        )
        with patcher:
            resp = client.post(
                "/v1/services/probe",
                json={
                    "host": "myhost",
                    "port": 443,
                    "health_path": "/api/health",
                    "scheme": "https",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["healthy"] is True
        # Verify the correct URL was called
        mock_inst.get.assert_called_once_with("https://myhost:443/api/health")

    def test_probe_translates_localhost_in_docker(self, client):
        """When DOCKER_HOST_GATEWAY is set, localhost is rewritten."""
        patcher, mock_inst = _mock_async_client(
            get_response=httpx.Response(200, json={"status": "ok"}),
        )
        with patch("app.routes.service_registration.get_settings") as mock_settings:
            mock_settings.return_value.DOCKER_HOST_GATEWAY = "host.docker.internal"
            with patcher:
                resp = client.post(
                    "/v1/services/probe",
                    json={"host": "localhost", "port": 8006},
                )

        assert resp.status_code == 200
        assert resp.json()["healthy"] is True
        mock_inst.get.assert_called_once_with(
            "http://host.docker.internal:8006/health"
        )

    def test_probe_translates_127_in_docker(self, client):
        """When DOCKER_HOST_GATEWAY is set, 127.0.0.1 is also rewritten."""
        patcher, mock_inst = _mock_async_client(
            get_response=httpx.Response(200, json={"status": "ok"}),
        )
        with patch("app.routes.service_registration.get_settings") as mock_settings:
            mock_settings.return_value.DOCKER_HOST_GATEWAY = "host.docker.internal"
            with patcher:
                resp = client.post(
                    "/v1/services/probe",
                    json={"host": "127.0.0.1", "port": 8006},
                )

        assert resp.status_code == 200
        mock_inst.get.assert_called_once_with(
            "http://host.docker.internal:8006/health"
        )

    def test_probe_no_translate_without_gateway(self, client):
        """When DOCKER_HOST_GATEWAY is empty, localhost is not rewritten."""
        patcher, mock_inst = _mock_async_client(
            get_response=httpx.Response(200, json={"status": "ok"}),
        )
        with patch("app.routes.service_registration.get_settings") as mock_settings:
            mock_settings.return_value.DOCKER_HOST_GATEWAY = ""
            with patcher:
                resp = client.post(
                    "/v1/services/probe",
                    json={"host": "localhost", "port": 8006},
                )

        assert resp.status_code == 200
        mock_inst.get.assert_called_once_with("http://localhost:8006/health")

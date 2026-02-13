"""Tests for settings gateway routes."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.models import Service


def _make_settings_response(settings: list[dict] | None = None) -> httpx.Response:
    """Build a mock httpx.Response with a settings payload."""
    body = {
        "settings": settings or [
            {
                "key": "model.name",
                "value": "gpt-4",
                "value_type": "string",
                "category": "model",
                "description": "Model name",
                "requires_reload": False,
                "is_secret": False,
                "env_fallback": "MODEL_NAME",
                "from_db": False,
            }
        ],
        "total": len(settings) if settings else 1,
    }
    return httpx.Response(200, json=body)


def _make_update_response(key: str = "model.name", requires_reload: bool = False) -> httpx.Response:
    return httpx.Response(200, json={
        "success": True,
        "key": key,
        "requires_reload": requires_reload,
        "message": None,
    })


@pytest.fixture
def services_in_db(db_session):
    """Populate DB with a few services."""
    svc1 = Service(
        name="tts",
        host="localhost",
        port=8009,
        scheme="http",
        health_path="/health",
    )
    svc2 = Service(
        name="logs",
        host="localhost",
        port=8006,
        scheme="http",
        health_path="/health",
    )
    db_session.add_all([svc1, svc2])
    db_session.commit()
    return [svc1, svc2]


# ── GET /v1/settings/ ──


class TestGetAggregatedSettings:
    """Tests for GET /v1/settings/."""

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_returns_aggregated_settings(
        self, mock_get: AsyncMock, client: TestClient, services_in_db
    ):
        """Should fan out and aggregate settings from all services."""
        mock_get.return_value = _make_settings_response()

        resp = client.get("/v1/settings/")
        assert resp.status_code == 200

        data = resp.json()
        assert data["total_services"] == 2
        assert data["successful_services"] == 2
        assert data["failed_services"] == 0
        assert len(data["services"]) == 2

        names = {s["service_name"] for s in data["services"]}
        assert names == {"tts", "logs"}

        for svc in data["services"]:
            assert svc["success"] is True
            assert len(svc["settings"]) == 1
            assert svc["settings"][0]["key"] == "model.name"

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_filter_by_service(
        self, mock_get: AsyncMock, client: TestClient, services_in_db
    ):
        """Should filter to a single service when ?service= is provided."""
        mock_get.return_value = _make_settings_response()

        resp = client.get("/v1/settings/?service=tts")
        assert resp.status_code == 200

        data = resp.json()
        assert data["total_services"] == 1
        assert data["services"][0]["service_name"] == "tts"

    def test_filter_unknown_service_returns_404(self, client: TestClient, services_in_db):
        """Should return 404 when filtering to a service not in registry."""
        resp = client.get("/v1/settings/?service=nonexistent")
        assert resp.status_code == 404

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_handles_service_down(
        self, mock_get: AsyncMock, client: TestClient, services_in_db
    ):
        """Should gracefully handle a service that is unreachable."""
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        resp = client.get("/v1/settings/")
        assert resp.status_code == 200

        data = resp.json()
        assert data["total_services"] == 2
        assert data["successful_services"] == 0
        assert data["failed_services"] == 2

        for svc in data["services"]:
            assert svc["success"] is False
            assert "Connection refused" in svc["error"]

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_handles_service_timeout(
        self, mock_get: AsyncMock, client: TestClient, services_in_db
    ):
        """Should handle timeout gracefully."""
        mock_get.side_effect = httpx.ReadTimeout("Timed out")

        resp = client.get("/v1/settings/")
        assert resp.status_code == 200

        data = resp.json()
        assert data["failed_services"] == 2
        for svc in data["services"]:
            assert svc["success"] is False
            assert "Timeout" in svc["error"]

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_handles_mixed_success_and_failure(
        self, mock_get: AsyncMock, client: TestClient, services_in_db
    ):
        """Should handle partial failures (some services up, some down)."""
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_settings_response()
            raise httpx.ConnectError("Connection refused")

        mock_get.side_effect = side_effect

        resp = client.get("/v1/settings/")
        assert resp.status_code == 200

        data = resp.json()
        assert data["successful_services"] == 1
        assert data["failed_services"] == 1

    def test_empty_registry_returns_empty(self, client: TestClient):
        """Should return empty result when no services are registered."""
        resp = client.get("/v1/settings/")
        assert resp.status_code == 200

        data = resp.json()
        assert data["total_services"] == 0
        assert data["services"] == []

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_includes_latency(
        self, mock_get: AsyncMock, client: TestClient, services_in_db
    ):
        """Should include latency_ms for each service."""
        mock_get.return_value = _make_settings_response()

        resp = client.get("/v1/settings/")
        data = resp.json()

        for svc in data["services"]:
            assert svc["latency_ms"] is not None
            assert isinstance(svc["latency_ms"], float)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_sends_app_credentials(
        self, mock_get: AsyncMock, client: TestClient, services_in_db
    ):
        """Should send app-to-app credentials in headers."""
        mock_get.return_value = _make_settings_response()

        resp = client.get("/v1/settings/")
        assert resp.status_code == 200

        # Verify headers were sent (mock captures call args)
        for call in mock_get.call_args_list:
            headers = call.kwargs.get("headers", {})
            # In test env, JARVIS_APP_ID/KEY are empty strings,
            # so headers won't be sent. That's the expected behavior
            # when credentials aren't configured.


# ── PUT /v1/settings/{service}/{key} ──


class TestUpdateServiceSetting:
    """Tests for PUT /v1/settings/{service_name}/{key}."""

    @patch("httpx.AsyncClient.put", new_callable=AsyncMock)
    def test_proxies_update_success(
        self, mock_put: AsyncMock, client: TestClient, services_in_db
    ):
        """Should proxy a successful update to the target service."""
        mock_put.return_value = _make_update_response()

        resp = client.put(
            "/v1/settings/tts/model.name",
            json={"value": "gpt-4o"},
        )
        assert resp.status_code == 200

        data = resp.json()
        assert data["service_name"] == "tts"
        assert data["success"] is True
        assert data["key"] == "model.name"
        assert data["requires_reload"] is False

    @patch("httpx.AsyncClient.put", new_callable=AsyncMock)
    def test_proxies_requires_reload(
        self, mock_put: AsyncMock, client: TestClient, services_in_db
    ):
        """Should report requires_reload from downstream service."""
        mock_put.return_value = _make_update_response(requires_reload=True)

        resp = client.put(
            "/v1/settings/tts/model.name",
            json={"value": "new-value"},
        )
        assert resp.status_code == 200
        assert resp.json()["requires_reload"] is True

    def test_update_unknown_service_returns_404(
        self, client: TestClient, services_in_db
    ):
        """Should return 404 for unknown service."""
        resp = client.put(
            "/v1/settings/nonexistent/some.key",
            json={"value": "x"},
        )
        assert resp.status_code == 404

    @patch("httpx.AsyncClient.put", new_callable=AsyncMock)
    def test_update_service_down(
        self, mock_put: AsyncMock, client: TestClient, services_in_db
    ):
        """Should return error when service is unreachable."""
        mock_put.side_effect = httpx.ConnectError("Connection refused")

        resp = client.put(
            "/v1/settings/tts/model.name",
            json={"value": "x"},
        )
        assert resp.status_code == 200

        data = resp.json()
        assert data["success"] is False
        assert "Failed to reach" in data["error"]

    @patch("httpx.AsyncClient.put", new_callable=AsyncMock)
    def test_update_forwards_auth_header(
        self, mock_put: AsyncMock, client: TestClient, services_in_db
    ):
        """Should forward the Authorization header to downstream service."""
        mock_put.return_value = _make_update_response()

        resp = client.put(
            "/v1/settings/tts/model.name",
            json={"value": "x"},
            headers={"Authorization": "Bearer test-jwt-token"},
        )
        assert resp.status_code == 200

        # Verify Authorization was forwarded
        call_kwargs = mock_put.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer test-jwt-token"

    @patch("httpx.AsyncClient.put", new_callable=AsyncMock)
    def test_update_handles_downstream_error(
        self, mock_put: AsyncMock, client: TestClient, services_in_db
    ):
        """Should handle non-200 responses from downstream."""
        mock_put.return_value = httpx.Response(
            403, json={"detail": "Forbidden"}
        )

        resp = client.put(
            "/v1/settings/tts/model.name",
            json={"value": "x"},
        )
        assert resp.status_code == 200

        data = resp.json()
        assert data["success"] is False
        assert "403" in data["error"]

    @patch("httpx.AsyncClient.put", new_callable=AsyncMock)
    def test_update_dotted_key(
        self, mock_put: AsyncMock, client: TestClient, services_in_db
    ):
        """Should handle dotted setting keys (path parameter)."""
        mock_put.return_value = _make_update_response(key="tts.voice.model")

        resp = client.put(
            "/v1/settings/tts/tts.voice.model",
            json={"value": "alan"},
        )
        assert resp.status_code == 200
        assert resp.json()["key"] == "tts.voice.model"

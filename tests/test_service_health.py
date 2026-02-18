"""Tests for service health check endpoints."""

from unittest.mock import AsyncMock

import httpx
from fastapi.testclient import TestClient

from helpers import mock_async_client


class TestServiceHealthCheck:
    """Tests for GET /services/{name}/health endpoint."""

    def test_health_check_service_not_found(self, client: TestClient):
        """Should return 404 when service doesn't exist."""
        response = client.get("/services/nonexistent/health")
        assert response.status_code == 404

    def test_health_check_service_healthy(self, client: TestClient, admin_headers: dict):
        """Should return healthy status when service responds 200."""
        client.post(
            "/services",
            json={"name": "healthy_svc", "host": "localhost", "port": 8080},
            headers=admin_headers,
        )

        patcher, _ = mock_async_client(
            target="app.routes.services.httpx.AsyncClient",
            get_response=httpx.Response(200),
        )
        with patcher:
            response = client.get("/services/healthy_svc/health")

        assert response.status_code == 200
        data = response.json()
        assert data["healthy"] is True
        assert data["latency_ms"] is not None
        assert data["error"] is None

    def test_health_check_service_unhealthy_status(self, client: TestClient, admin_headers: dict):
        """Should return unhealthy when service responds non-200."""
        client.post(
            "/services",
            json={"name": "unhealthy_svc", "host": "localhost", "port": 8080},
            headers=admin_headers,
        )

        patcher, _ = mock_async_client(
            target="app.routes.services.httpx.AsyncClient",
            get_response=httpx.Response(500),
        )
        with patcher:
            response = client.get("/services/unhealthy_svc/health")

        assert response.status_code == 200
        data = response.json()
        assert data["healthy"] is False
        assert "HTTP 500" in data["error"]

    def test_health_check_connection_refused(self, client: TestClient, admin_headers: dict):
        """Should handle connection refused gracefully."""
        client.post(
            "/services",
            json={"name": "offline_svc", "host": "localhost", "port": 8080},
            headers=admin_headers,
        )

        patcher, _ = mock_async_client(
            target="app.routes.services.httpx.AsyncClient",
            get_side_effect=httpx.ConnectError("Connection refused"),
        )
        with patcher:
            response = client.get("/services/offline_svc/health")

        assert response.status_code == 200
        data = response.json()
        assert data["healthy"] is False
        assert "Connection refused" in data["error"]

    def test_health_check_timeout(self, client: TestClient, admin_headers: dict):
        """Should handle timeout gracefully."""
        client.post(
            "/services",
            json={"name": "slow_svc", "host": "localhost", "port": 8080},
            headers=admin_headers,
        )

        patcher, _ = mock_async_client(
            target="app.routes.services.httpx.AsyncClient",
            get_side_effect=httpx.TimeoutException("Timeout"),
        )
        with patcher:
            response = client.get("/services/slow_svc/health")

        assert response.status_code == 200
        data = response.json()
        assert data["healthy"] is False
        assert "Timeout" in data["error"]


class TestAllServicesHealth:
    """Tests for GET /services/health endpoint."""

    def test_health_check_no_services(self, client: TestClient):
        """Should return empty results when no services registered."""
        response = client.get("/services/health")

        assert response.status_code == 200
        data = response.json()
        assert data["services"] == {}
        assert data["healthy_count"] == 0
        assert data["total_count"] == 0

    def test_health_check_multiple_services(self, client: TestClient, admin_headers: dict):
        """Should check health of all services."""
        client.post(
            "/services",
            json={"name": "svc_a", "host": "localhost", "port": 8001},
            headers=admin_headers,
        )
        client.post(
            "/services",
            json={"name": "svc_b", "host": "localhost", "port": 8002},
            headers=admin_headers,
        )

        # Mock: svc_a healthy, svc_b unhealthy
        mock_response_ok = AsyncMock()
        mock_response_ok.status_code = 200

        async def mock_get(url):
            if "8001" in url:
                return mock_response_ok
            raise httpx.ConnectError("Connection refused")

        patcher, mock_inst = mock_async_client(
            target="app.routes.services.httpx.AsyncClient",
        )
        mock_inst.get = mock_get

        with patcher:
            response = client.get("/services/health")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 2
        assert data["healthy_count"] == 1
        assert data["services"]["svc_a"]["healthy"] is True
        assert data["services"]["svc_b"]["healthy"] is False

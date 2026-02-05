"""Tests for service health check endpoints."""
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient


class TestServiceHealthCheck:
    """Tests for GET /services/{name}/health endpoint."""

    def test_health_check_service_not_found(self, client: TestClient):
        """Should return 404 when service doesn't exist."""
        response = client.get("/services/nonexistent/health")

        assert response.status_code == 404

    @patch("app.routes.services.httpx.AsyncClient")
    def test_health_check_service_healthy(
        self, mock_client_class, client: TestClient, admin_headers: dict
    ):
        """Should return healthy status when service responds 200."""
        # Create a service
        client.post(
            "/services",
            json={"name": "healthy_svc", "host": "localhost", "port": 8080},
            headers=admin_headers
        )

        # Mock the httpx client
        mock_response = AsyncMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        response = client.get("/services/healthy_svc/health")

        assert response.status_code == 200
        data = response.json()
        assert data["healthy"] is True
        assert data["latency_ms"] is not None
        assert data["error"] is None

    @patch("app.routes.services.httpx.AsyncClient")
    def test_health_check_service_unhealthy_status(
        self, mock_client_class, client: TestClient, admin_headers: dict
    ):
        """Should return unhealthy when service responds non-200."""
        client.post(
            "/services",
            json={"name": "unhealthy_svc", "host": "localhost", "port": 8080},
            headers=admin_headers
        )

        mock_response = AsyncMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        response = client.get("/services/unhealthy_svc/health")

        assert response.status_code == 200
        data = response.json()
        assert data["healthy"] is False
        assert "HTTP 500" in data["error"]

    @patch("app.routes.services.httpx.AsyncClient")
    def test_health_check_connection_refused(
        self, mock_client_class, client: TestClient, admin_headers: dict
    ):
        """Should handle connection refused gracefully."""
        client.post(
            "/services",
            json={"name": "offline_svc", "host": "localhost", "port": 8080},
            headers=admin_headers
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        response = client.get("/services/offline_svc/health")

        assert response.status_code == 200
        data = response.json()
        assert data["healthy"] is False
        assert "Connection refused" in data["error"]

    @patch("app.routes.services.httpx.AsyncClient")
    def test_health_check_timeout(
        self, mock_client_class, client: TestClient, admin_headers: dict
    ):
        """Should handle timeout gracefully."""
        client.post(
            "/services",
            json={"name": "slow_svc", "host": "localhost", "port": 8080},
            headers=admin_headers
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

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

    @patch("app.routes.services.httpx.AsyncClient")
    def test_health_check_multiple_services(
        self, mock_client_class, client: TestClient, admin_headers: dict
    ):
        """Should check health of all services."""
        # Create multiple services
        client.post(
            "/services",
            json={"name": "svc_a", "host": "localhost", "port": 8001},
            headers=admin_headers
        )
        client.post(
            "/services",
            json={"name": "svc_b", "host": "localhost", "port": 8002},
            headers=admin_headers
        )

        # Mock: svc_a healthy, svc_b unhealthy
        mock_response_ok = AsyncMock()
        mock_response_ok.status_code = 200

        call_count = 0
        async def mock_get(url):
            nonlocal call_count
            call_count += 1
            if "8001" in url:
                return mock_response_ok
            else:
                raise httpx.ConnectError("Connection refused")

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        response = client.get("/services/health")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 2
        assert data["healthy_count"] == 1
        assert data["services"]["svc_a"]["healthy"] is True
        assert data["services"]["svc_b"]["healthy"] is False

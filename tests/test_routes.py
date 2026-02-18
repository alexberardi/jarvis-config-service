"""Tests for config service routes."""

import pytest
from unittest.mock import patch, AsyncMock
import httpx


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_ok(self, client):
        """Test health endpoint returns ok status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_is_unauthenticated(self, client):
        """Health endpoint should not require authentication."""
        response = client.get("/health")
        assert response.status_code == 200


class TestInfoEndpoint:
    """Tests for /info endpoint."""

    def test_info_returns_service_identity(self, client):
        """Info endpoint should return the service name for network discovery."""
        response = client.get("/info")
        assert response.status_code == 200
        assert response.json() == {"service": "jarvis-config-service"}

    def test_info_is_unauthenticated(self, client):
        """Info endpoint should not require authentication."""
        response = client.get("/info")
        assert response.status_code == 200


class TestListServices:
    """Tests for GET /services endpoint."""

    def test_list_services_empty(self, client):
        """Test listing services when none exist."""
        response = client.get("/services")
        assert response.status_code == 200
        data = response.json()
        assert data["services"] == []

    def test_list_services_returns_all(self, client, sample_service, admin_headers):
        """Test listing services returns all registered services."""
        response = client.get("/services")
        assert response.status_code == 200
        data = response.json()
        assert len(data["services"]) == 1
        assert data["services"][0]["name"] == "logs"

    def test_list_services_dockerized_style(self, client, sample_service):
        """Test listing services with dockerized URL style."""
        response = client.get("/services?style=dockerized")
        assert response.status_code == 200
        data = response.json()
        assert "host.docker.internal" in data["services"][0]["url"]


class TestGetService:
    """Tests for GET /services/{name} endpoint."""

    def test_get_service_found(self, client, sample_service):
        """Test getting an existing service."""
        response = client.get("/services/logs")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "logs"
        assert data["port"] == 8006
        assert data["url"] == "http://localhost:8006"

    def test_get_service_not_found(self, client):
        """Test getting a non-existent service."""
        response = client.get("/services/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_get_service_dockerized_style(self, client, sample_service):
        """Test getting service with dockerized URL style."""
        response = client.get("/services/logs?style=dockerized")
        assert response.status_code == 200
        data = response.json()
        assert "host.docker.internal" in data["url"]


class TestCreateService:
    """Tests for POST /services endpoint."""

    def test_create_service_success(self, client, admin_headers, sample_service_data):
        """Test creating a new service."""
        response = client.post("/services", json=sample_service_data, headers=admin_headers)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_service_data["name"]
        assert data["port"] == sample_service_data["port"]
        assert "id" in data
        assert "url" in data

    def test_create_service_requires_admin(self, client, sample_service_data):
        """Test creating service without admin token fails."""
        response = client.post("/services", json=sample_service_data)
        assert response.status_code == 422  # Missing required header

    def test_create_service_invalid_token(self, client, sample_service_data):
        """Test creating service with invalid token fails."""
        response = client.post(
            "/services",
            json=sample_service_data,
            headers={"X-Admin-Token": "wrong-token"},
        )
        assert response.status_code == 401

    def test_create_service_duplicate_name(self, client, admin_headers, sample_service):
        """Test creating service with duplicate name fails."""
        response = client.post(
            "/services",
            json={
                "name": "logs",  # Already exists
                "host": "localhost",
                "port": 9999,
            },
            headers=admin_headers,
        )
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_create_service_invalid_port(self, client, admin_headers):
        """Test creating service with invalid port fails."""
        response = client.post(
            "/services",
            json={
                "name": "invalid-service",
                "host": "localhost",
                "port": 99999,  # Out of range
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_create_service_invalid_scheme(self, client, admin_headers):
        """Test creating service with invalid scheme fails."""
        response = client.post(
            "/services",
            json={
                "name": "invalid-service",
                "host": "localhost",
                "port": 8000,
                "scheme": "ftp",  # Invalid
            },
            headers=admin_headers,
        )
        assert response.status_code == 422


class TestUpdateService:
    """Tests for PUT /services/{name} endpoint."""

    def test_update_service_success(self, client, admin_headers, sample_service):
        """Test updating an existing service."""
        response = client.put(
            "/services/logs",
            json={"port": 9006, "description": "Updated logging service"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["port"] == 9006
        assert data["description"] == "Updated logging service"

    def test_update_service_not_found(self, client, admin_headers):
        """Test updating non-existent service fails."""
        response = client.put(
            "/services/nonexistent",
            json={"port": 9999},
            headers=admin_headers,
        )
        assert response.status_code == 404

    def test_update_service_requires_admin(self, client, sample_service):
        """Test updating service without admin token fails."""
        response = client.put("/services/logs", json={"port": 9999})
        assert response.status_code == 422


class TestDeleteService:
    """Tests for DELETE /services/{name} endpoint."""

    def test_delete_service_success(self, client, admin_headers, sample_service):
        """Test deleting an existing service."""
        response = client.delete("/services/logs", headers=admin_headers)
        assert response.status_code == 204

        # Verify it's gone
        response = client.get("/services/logs")
        assert response.status_code == 404

    def test_delete_service_not_found(self, client, admin_headers):
        """Test deleting non-existent service fails."""
        response = client.delete("/services/nonexistent", headers=admin_headers)
        assert response.status_code == 404

    def test_delete_service_requires_admin(self, client, sample_service):
        """Test deleting service without admin token fails."""
        response = client.delete("/services/logs")
        assert response.status_code == 422


class TestServiceHealth:
    """Tests for service health check endpoints."""

    @pytest.mark.asyncio
    async def test_check_service_health_success(self, client, sample_service):
        """Test checking health of a healthy service."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            response = client.get("/services/logs/health")
            assert response.status_code == 200
            data = response.json()
            assert data["healthy"] is True

    @pytest.mark.asyncio
    async def test_check_service_health_unhealthy(self, client, sample_service):
        """Test checking health of an unhealthy service."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_response = AsyncMock()
            mock_response.status_code = 500
            mock_get.return_value = mock_response

            response = client.get("/services/logs/health")
            assert response.status_code == 200
            data = response.json()
            assert data["healthy"] is False
            assert "HTTP 500" in data["error"]

    @pytest.mark.asyncio
    async def test_check_service_health_connection_error(self, client, sample_service):
        """Test checking health when service is unreachable."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ConnectError("Connection refused")

            response = client.get("/services/logs/health")
            assert response.status_code == 200
            data = response.json()
            assert data["healthy"] is False
            assert "Connection refused" in data["error"]

    @pytest.mark.asyncio
    async def test_check_service_health_timeout(self, client, sample_service):
        """Test checking health when service times out."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Timeout")

            response = client.get("/services/logs/health")
            assert response.status_code == 200
            data = response.json()
            assert data["healthy"] is False
            assert "Timeout" in data["error"]

    def test_check_service_health_not_found(self, client):
        """Test checking health of non-existent service."""
        response = client.get("/services/nonexistent/health")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_check_all_services_health(self, client, sample_service):
        """Test checking health of all services."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            response = client.get("/services/health")
            assert response.status_code == 200
            data = response.json()
            assert data["total_count"] == 1
            assert data["healthy_count"] == 1
            assert "logs" in data["services"]

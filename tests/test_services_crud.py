"""Tests for services CRUD operations."""
import pytest
from fastapi.testclient import TestClient


class TestListServices:
    """Tests for GET /services endpoint."""

    def test_list_services_empty(self, client: TestClient):
        """Should return empty list when no services registered."""
        response = client.get("/services")

        assert response.status_code == 200
        data = response.json()
        assert data["services"] == []

    def test_list_services_returns_all(
        self, client: TestClient, admin_headers: dict, sample_service_data: dict, another_service_data: dict
    ):
        """Should return all registered services."""
        # Create two services
        client.post("/services", json=sample_service_data, headers=admin_headers)
        client.post("/services", json=another_service_data, headers=admin_headers)

        response = client.get("/services")

        assert response.status_code == 200
        data = response.json()
        assert len(data["services"]) == 2
        names = [s["name"] for s in data["services"]]
        assert "test_service" in names
        assert "another_service" in names

    def test_list_services_ordered_by_name(
        self, client: TestClient, admin_headers: dict
    ):
        """Services should be returned ordered by name."""
        # Create services in non-alphabetical order
        client.post("/services", json={"name": "zebra", "host": "localhost", "port": 8080}, headers=admin_headers)
        client.post("/services", json={"name": "alpha", "host": "localhost", "port": 8081}, headers=admin_headers)
        client.post("/services", json={"name": "middle", "host": "localhost", "port": 8082}, headers=admin_headers)

        response = client.get("/services")

        data = response.json()
        names = [s["name"] for s in data["services"]]
        assert names == ["alpha", "middle", "zebra"]

    def test_list_services_dockerized_style(
        self, client: TestClient, admin_headers: dict
    ):
        """Dockerized style should replace localhost with host.docker.internal."""
        client.post(
            "/services",
            json={"name": "local_svc", "host": "localhost", "port": 8080},
            headers=admin_headers
        )

        response = client.get("/services?style=dockerized")

        data = response.json()
        assert len(data["services"]) == 1
        assert data["services"][0]["url"] == "http://host.docker.internal:8080"

    def test_list_services_dockerized_preserves_non_localhost(
        self, client: TestClient, admin_headers: dict
    ):
        """Dockerized style should not modify non-localhost hosts."""
        client.post(
            "/services",
            json={"name": "remote_svc", "host": "192.168.1.100", "port": 8080},
            headers=admin_headers
        )

        response = client.get("/services?style=dockerized")

        data = response.json()
        assert data["services"][0]["url"] == "http://192.168.1.100:8080"

    def test_list_services_no_auth_required(self, client: TestClient):
        """List services should not require authentication."""
        response = client.get("/services")
        assert response.status_code == 200


class TestGetService:
    """Tests for GET /services/{name} endpoint."""

    def test_get_service_found(
        self, client: TestClient, admin_headers: dict, sample_service_data: dict
    ):
        """Should return service when it exists."""
        client.post("/services", json=sample_service_data, headers=admin_headers)

        response = client.get("/services/test_service")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test_service"
        assert data["host"] == "localhost"
        assert data["port"] == 8080
        assert data["url"] == "http://localhost:8080"

    def test_get_service_not_found(self, client: TestClient):
        """Should return 404 when service doesn't exist."""
        response = client.get("/services/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_service_dockerized_style(
        self, client: TestClient, admin_headers: dict
    ):
        """Should support dockerized style for single service."""
        client.post(
            "/services",
            json={"name": "local_svc", "host": "127.0.0.1", "port": 3000},
            headers=admin_headers
        )

        response = client.get("/services/local_svc?style=dockerized")

        data = response.json()
        assert data["url"] == "http://host.docker.internal:3000"


class TestCreateService:
    """Tests for POST /services endpoint."""

    def test_create_service_success(
        self, client: TestClient, admin_headers: dict, sample_service_data: dict
    ):
        """Should create service with valid data and admin token."""
        response = client.post("/services", json=sample_service_data, headers=admin_headers)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test_service"
        assert data["host"] == "localhost"
        assert data["port"] == 8080
        assert data["scheme"] == "http"
        assert data["url"] == "http://localhost:8080"
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_service_minimal_data(self, client: TestClient, admin_headers: dict):
        """Should create service with only required fields."""
        minimal_data = {"name": "minimal", "host": "localhost", "port": 8000}

        response = client.post("/services", json=minimal_data, headers=admin_headers)

        assert response.status_code == 201
        data = response.json()
        assert data["scheme"] == "http"  # default
        assert data["health_path"] == "/health"  # default

    def test_create_service_https(self, client: TestClient, admin_headers: dict):
        """Should support https scheme."""
        https_data = {"name": "secure", "host": "example.com", "port": 443, "scheme": "https"}

        response = client.post("/services", json=https_data, headers=admin_headers)

        assert response.status_code == 201
        assert response.json()["url"] == "https://example.com:443"

    def test_create_service_duplicate_name(
        self, client: TestClient, admin_headers: dict, sample_service_data: dict
    ):
        """Should return 409 when service name already exists."""
        client.post("/services", json=sample_service_data, headers=admin_headers)

        response = client.post("/services", json=sample_service_data, headers=admin_headers)

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    def test_create_service_requires_admin(
        self, client: TestClient, sample_service_data: dict
    ):
        """Should return 422 when admin token is missing."""
        response = client.post("/services", json=sample_service_data)

        assert response.status_code == 422  # Missing required header

    def test_create_service_invalid_admin_token(
        self, client: TestClient, invalid_admin_headers: dict, sample_service_data: dict
    ):
        """Should return 401 when admin token is invalid."""
        response = client.post("/services", json=sample_service_data, headers=invalid_admin_headers)

        assert response.status_code == 401

    def test_create_service_invalid_port_too_high(self, client: TestClient, admin_headers: dict):
        """Should reject port above 65535."""
        data = {"name": "invalid", "host": "localhost", "port": 70000}

        response = client.post("/services", json=data, headers=admin_headers)

        assert response.status_code == 422

    def test_create_service_invalid_port_zero(self, client: TestClient, admin_headers: dict):
        """Should reject port 0."""
        data = {"name": "invalid", "host": "localhost", "port": 0}

        response = client.post("/services", json=data, headers=admin_headers)

        assert response.status_code == 422

    def test_create_service_invalid_scheme(self, client: TestClient, admin_headers: dict):
        """Should reject invalid scheme."""
        data = {"name": "invalid", "host": "localhost", "port": 8080, "scheme": "ftp"}

        response = client.post("/services", json=data, headers=admin_headers)

        assert response.status_code == 422


class TestUpdateService:
    """Tests for PUT /services/{name} endpoint."""

    def test_update_service_success(
        self, client: TestClient, admin_headers: dict, sample_service_data: dict
    ):
        """Should update service fields."""
        client.post("/services", json=sample_service_data, headers=admin_headers)

        response = client.put(
            "/services/test_service",
            json={"port": 9000, "description": "Updated description"},
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["port"] == 9000
        assert data["description"] == "Updated description"
        assert data["host"] == "localhost"  # Unchanged

    def test_update_service_partial(
        self, client: TestClient, admin_headers: dict, sample_service_data: dict
    ):
        """Should support partial updates."""
        client.post("/services", json=sample_service_data, headers=admin_headers)

        response = client.put(
            "/services/test_service",
            json={"host": "newhost.local"},
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["host"] == "newhost.local"
        assert data["port"] == 8080  # Unchanged

    def test_update_service_not_found(self, client: TestClient, admin_headers: dict):
        """Should return 404 when service doesn't exist."""
        response = client.put(
            "/services/nonexistent",
            json={"port": 9000},
            headers=admin_headers
        )

        assert response.status_code == 404

    def test_update_service_requires_admin(
        self, client: TestClient, admin_headers: dict, sample_service_data: dict
    ):
        """Should require admin token."""
        client.post("/services", json=sample_service_data, headers=admin_headers)

        response = client.put("/services/test_service", json={"port": 9000})

        assert response.status_code == 422


class TestDeleteService:
    """Tests for DELETE /services/{name} endpoint."""

    def test_delete_service_success(
        self, client: TestClient, admin_headers: dict, sample_service_data: dict
    ):
        """Should delete existing service."""
        client.post("/services", json=sample_service_data, headers=admin_headers)

        response = client.delete("/services/test_service", headers=admin_headers)

        assert response.status_code == 204

        # Verify service is gone
        get_response = client.get("/services/test_service")
        assert get_response.status_code == 404

    def test_delete_service_not_found(self, client: TestClient, admin_headers: dict):
        """Should return 404 when service doesn't exist."""
        response = client.delete("/services/nonexistent", headers=admin_headers)

        assert response.status_code == 404

    def test_delete_service_requires_admin(
        self, client: TestClient, admin_headers: dict, sample_service_data: dict
    ):
        """Should require admin token."""
        client.post("/services", json=sample_service_data, headers=admin_headers)

        response = client.delete("/services/test_service")

        assert response.status_code == 422

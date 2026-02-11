"""Tests for the config service /info endpoint."""

from fastapi.testclient import TestClient


def test_info_endpoint_returns_service_identity(client: TestClient):
    """Info endpoint should return the service name for network discovery."""
    response = client.get("/info")

    assert response.status_code == 200
    assert response.json() == {"service": "jarvis-config-service"}


def test_info_endpoint_is_unauthenticated(client: TestClient):
    """Info endpoint should not require authentication."""
    # No headers provided
    response = client.get("/info")

    assert response.status_code == 200

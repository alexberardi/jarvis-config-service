"""Tests for the config service health endpoint."""
import pytest
from fastapi.testclient import TestClient


def test_health_endpoint_returns_ok(client: TestClient):
    """Health endpoint should return status ok."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_endpoint_is_unauthenticated(client: TestClient):
    """Health endpoint should not require authentication."""
    # No headers provided
    response = client.get("/health")

    assert response.status_code == 200

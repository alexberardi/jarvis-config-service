"""Tests for Service model."""

import pytest
from app.models import Service


class TestServiceModel:
    """Tests for Service model URL methods."""

    @pytest.fixture
    def service(self):
        """Create a test service instance."""
        return Service(
            id=1,
            name="jarvis-test",
            host="localhost",
            port=8000,
            scheme="http",
            health_path="/health",
        )

    def test_get_url_default(self, service):
        """Test URL generation with defaults."""
        assert service.get_url() == "http://localhost:8000"

    def test_get_url_dockerized_localhost(self, service):
        """Test URL generation with dockerized localhost."""
        assert service.get_url(dockerized=True) == "http://host.docker.internal:8000"

    def test_get_url_dockerized_127(self):
        """Test URL generation with dockerized 127.0.0.1."""
        service = Service(
            name="test",
            host="127.0.0.1",
            port=8000,
            scheme="http",
        )
        assert service.get_url(dockerized=True) == "http://host.docker.internal:8000"

    def test_get_url_dockerized_non_localhost(self):
        """Test URL generation with dockerized non-localhost host."""
        service = Service(
            name="test",
            host="example.com",
            port=8000,
            scheme="http",
        )
        # Should not replace non-localhost hosts
        assert service.get_url(dockerized=True) == "http://example.com:8000"

    def test_url_property(self, service):
        """Test url property returns non-dockerized URL."""
        assert service.url == "http://localhost:8000"

    def test_get_health_url(self, service):
        """Test health URL generation."""
        assert service.get_health_url() == "http://localhost:8000/health"

    def test_get_health_url_dockerized(self, service):
        """Test dockerized health URL generation."""
        assert service.get_health_url(dockerized=True) == "http://host.docker.internal:8000/health"

    def test_health_url_property(self, service):
        """Test health_url property."""
        assert service.health_url == "http://localhost:8000/health"

    def test_https_scheme(self):
        """Test HTTPS scheme in URL."""
        service = Service(
            name="secure-test",
            host="localhost",
            port=443,
            scheme="https",
            health_path="/api/health",
        )
        assert service.url == "https://localhost:443"
        assert service.health_url == "https://localhost:443/api/health"

    def test_custom_health_path(self):
        """Test custom health path."""
        service = Service(
            name="custom-test",
            host="localhost",
            port=8000,
            scheme="http",
            health_path="/api/v1/healthz",
        )
        assert service.health_url == "http://localhost:8000/api/v1/healthz"

    def test_get_url_remote_host_replaces_localhost(self, service):
        """Test remote_host replaces localhost."""
        assert service.get_url(remote_host="10.0.0.5") == "http://10.0.0.5:8000"

    def test_get_url_remote_host_replaces_127(self):
        """Test remote_host replaces 127.0.0.1."""
        service = Service(
            name="test",
            host="127.0.0.1",
            port=8000,
            scheme="http",
        )
        assert service.get_url(remote_host="10.0.0.5") == "http://10.0.0.5:8000"

    def test_get_url_remote_host_skips_non_localhost(self):
        """Test remote_host does NOT replace non-localhost hosts."""
        service = Service(
            name="test",
            host="192.168.1.50",
            port=8000,
            scheme="http",
        )
        assert service.get_url(remote_host="10.0.0.5") == "http://192.168.1.50:8000"

    def test_get_url_remote_host_takes_precedence_over_dockerized(self, service):
        """Test remote_host takes precedence over dockerized flag."""
        assert service.get_url(dockerized=True, remote_host="10.0.0.5") == "http://10.0.0.5:8000"

    def test_get_health_url_remote_host(self, service):
        """Test health URL with remote_host."""
        assert service.get_health_url(remote_host="10.0.0.5") == "http://10.0.0.5:8000/health"

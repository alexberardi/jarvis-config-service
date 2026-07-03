"""Registration writes must validate the host is a bare hostname/IP.

A registered host becomes a discovery URL handed to every service, so a value
carrying a scheme/path/port/creds could redirect callers or smuggle a URL.
"""
import pytest
from pydantic import ValidationError

from app.schemas import ServiceCreate, ServiceUpdate, HealthProbeRequest, validate_host


class TestValidateHost:
    @pytest.mark.parametrize(
        "h",
        ["localhost", "host.docker.internal", "10.0.0.107", "jarvis-auth", "my_service", "[::1]"],
    )
    def test_accepts_bare_hosts(self, h):
        assert validate_host(h) == h

    @pytest.mark.parametrize(
        "h",
        [
            "http://evil",
            "https://evil.com/x",
            "evil/path",
            "host:1234",
            "user@host",
            "1.2.3.4 evil",
            "a b",
            "has/slash",
            "http://169.254.169.254/latest",
            "",
        ],
    )
    def test_rejects_urls_and_junk(self, h):
        with pytest.raises(ValueError):
            validate_host(h)

    def test_none_passes_through(self):
        assert validate_host(None) is None


class TestSchemaEnforcement:
    def test_service_create_rejects_url_host(self):
        with pytest.raises(ValidationError):
            ServiceCreate(name="x", host="http://evil", port=80)

    def test_service_create_accepts_hostname(self):
        assert ServiceCreate(name="x", host="jarvis-auth", port=7701).host == "jarvis-auth"

    def test_service_update_rejects_url_host(self):
        with pytest.raises(ValidationError):
            ServiceUpdate(host="http://evil/x")

    def test_service_update_allows_omitted_host(self):
        assert ServiceUpdate(port=1234).host is None

    def test_probe_rejects_url_host(self):
        with pytest.raises(ValidationError):
            HealthProbeRequest(host="http://evil", port=80)

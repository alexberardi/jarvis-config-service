"""Pytest fixtures for jarvis-config-service tests."""

import os

# Set test environment BEFORE importing app modules
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JARVIS_CONFIG_ADMIN_TOKEN"] = "test-admin-token"
os.environ["JARVIS_AUTH_URL"] = "http://localhost:8007"
os.environ["JARVIS_AUTH_ADMIN_TOKEN"] = "test-auth-admin-token"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Now import app modules after env is set
from app.database import Base, get_db
from app.main import app, superuser_auth
from app.models import Service


# Create test engine with SQLite
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


# Enable foreign keys for SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _mock_superuser_auth():
    """Mock superuser auth that always succeeds."""
    return {"auth_type": "superuser_jwt", "user_id": 1, "email": "admin@test.com"}


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Create a test client with overridden database dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[superuser_auth] = _mock_superuser_auth

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def admin_headers():
    """Headers for CRUD admin-authenticated requests (X-Admin-Token)."""
    return {"X-Admin-Token": "test-admin-token"}


@pytest.fixture
def registration_headers():
    """Headers for registration routes (X-Jarvis-Admin-Token)."""
    return {"X-Jarvis-Admin-Token": "test-auth-admin-token"}


@pytest.fixture
def invalid_admin_headers():
    """Headers with invalid admin token."""
    return {"X-Admin-Token": "wrong-token"}


@pytest.fixture
def sample_service_data():
    """Sample service data for creating services."""
    return {
        "name": "test_service",
        "host": "localhost",
        "port": 8080,
        "scheme": "http",
        "health_path": "/health",
        "description": "A test service",
    }


@pytest.fixture
def another_service_data():
    """Another sample service for testing multiple services."""
    return {
        "name": "another_service",
        "host": "192.168.1.100",
        "port": 9000,
        "scheme": "https",
        "health_path": "/api/health",
        "description": "Another test service",
    }


@pytest.fixture
def sample_service(db_session) -> Service:
    """Create a sample service in the database."""
    service = Service(
        name="logs",
        host="localhost",
        port=8006,
        scheme="http",
        health_path="/health",
        description="Logging service",
    )
    db_session.add(service)
    db_session.commit()
    db_session.refresh(service)
    return service



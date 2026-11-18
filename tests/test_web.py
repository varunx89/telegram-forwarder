from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from web_app import app, lifespan
from telegram_client import service

client = TestClient(app)

def test_health_endpoint_healthy():
    """Verify /health returns HTTP 200 when service is running and connected (VULN-04)."""
    mock_client = MagicMock()
    mock_client.is_connected = MagicMock(return_value=True)

    with patch.object(service, "client", mock_client), \
         patch.object(service, "is_running", True), \
         patch.object(service, "is_connected", True):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["running"] is True
        assert data["connected"] is True
        assert "ipv6" in data

def test_health_endpoint_disconnected():
    """Verify /health returns HTTP 503 when service is uninitialized or disconnected (VULN-04)."""
    with patch.object(service, "client", None), \
         patch.object(service, "is_running", False), \
         patch.object(service, "is_connected", False):
        response = client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "disconnected"
        assert data["running"] is False
        assert data["connected"] is False

def test_health_endpoint_degraded():
    """Verify /health returns HTTP 503 degraded when service is running but client disconnected."""
    mock_client = MagicMock()
    mock_client.is_connected = MagicMock(return_value=False)

    with patch.object(service, "client", mock_client), \
         patch.object(service, "is_running", True), \
         patch.object(service, "is_connected", False):
        response = client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["running"] is True
        assert data["connected"] is False

def test_live_endpoint():
    """Verify /live endpoint returns HTTP 200 for process liveness checks."""
    response = client.get("/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}

def test_root_endpoint():
    """Verify / root endpoint returns service identification."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "telegram-forwarder"
    assert data["status"] == "active"

@pytest.mark.asyncio
async def test_lifespan_startup_and_shutdown():
    """Verify clean FastAPI lifespan execution without router monkey-patching (VULN-10)."""
    with patch.object(service, "initialize", new_callable=AsyncMock) as mock_init, \
         patch.object(service, "shutdown", new_callable=AsyncMock) as mock_shutdown:
        async with lifespan(app):
            mock_init.assert_awaited_once()
            assert mock_shutdown.call_count == 0
        mock_shutdown.assert_awaited_once()

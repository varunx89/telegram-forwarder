import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from config import settings
from telegram_client import service
from web_app import app, EXPECTED_TOKEN

client = TestClient(app)

def test_public_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

def test_unauthenticated_dashboard_redirects():
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

def test_unauthenticated_api_rejected():
    response = client.post("/api/auth/send-code", json={"phone": "+1234567890"})
    assert response.status_code == 401

def test_login_invalid_password():
    response = client.post("/login", data={"password": "wrong-password"})
    assert response.status_code == 401
    assert "Invalid Password" in response.text

def test_login_valid_password():
    response = client.post(
        "/login",
        data={"password": settings.ADMIN_PASSWORD},
        follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/"
    assert settings.COOKIE_NAME in response.cookies
    assert response.cookies[settings.COOKIE_NAME] == EXPECTED_TOKEN

def test_authenticated_view():
    client.cookies.set(settings.COOKIE_NAME, EXPECTED_TOKEN)
    response = client.get("/")
    assert response.status_code == 200

@patch.object(service, 'send_code', new_callable=AsyncMock)
def test_api_send_code(mock_send_code):
    mock_send_code.return_value = {"success": True, "message": "Code sent"}
    client.cookies.set(settings.COOKIE_NAME, EXPECTED_TOKEN)
    
    response = client.post("/api/auth/send-code", json={"phone": "+1234567890"})
    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Code sent"}
    mock_send_code.assert_awaited_once_with("+1234567890")

@patch.object(service, 'verify_code', new_callable=AsyncMock)
def test_api_verify_code(mock_verify_code):
    mock_verify_code.return_value = {"success": True, "message": "Verified"}
    client.cookies.set(settings.COOKIE_NAME, EXPECTED_TOKEN)
    
    response = client.post("/api/auth/verify-code", json={"code": "54321"})
    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Verified"}
    mock_verify_code.assert_awaited_once_with("54321")

@patch.object(service, 'submit_password', new_callable=AsyncMock)
def test_api_submit_password(mock_submit_pwd):
    mock_submit_pwd.return_value = {"success": True, "message": "2FA verified"}
    client.cookies.set(settings.COOKIE_NAME, EXPECTED_TOKEN)
    
    response = client.post("/api/auth/submit-password", json={"password": "secret2fa"})
    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "2FA verified"}
    mock_submit_pwd.assert_awaited_once_with("secret2fa")

@patch.object(service, 'logout', new_callable=AsyncMock)
def test_api_logout(mock_logout):
    mock_logout.return_value = {"success": True, "message": "Logged out"}
    client.cookies.set(settings.COOKIE_NAME, EXPECTED_TOKEN)
    
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Logged out"}
    mock_logout.assert_awaited_once()

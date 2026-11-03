import pytest
from fastapi.testclient import TestClient
from web_app import app
from telegram_client import service

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "running" in data
    assert "connected" in data

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "telegram-forwarder"
    assert data["status"] == "active"


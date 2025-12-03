import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_discover_endpoint():
    response = client.get("/discover.json")
    assert response.status_code == 200
    data = response.json()
    assert "FriendlyName" in data
    assert "BaseURL" in data
    assert data["TunerCount"] == 1

def test_lineup_status():
    response = client.get("/lineup_status.json")
    assert response.status_code == 200
    data = response.json()
    assert "ScanPossible" in data
    assert data["Source"] == "Cable"

def test_lineup_json():
    response = client.get("/lineup.json")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_epg_xml():
    response = client.get("/epg.xml")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml"
    assert "<?xml" in response.text

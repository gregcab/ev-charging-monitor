"""Tests des API JSON du dashboard."""

import json


def test_api_stations(client):
    response = client.get("/api/stations")
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) == 3
    ids = {s["id"] for s in data}
    assert ids == {"station-paris-1", "station-paris-2", "station-lyon-1"}
    for station in data:
        assert "latest" in station


def test_api_dashboard(client):
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.get_json()
    assert "stations" in data
    assert "interval" in data
    assert "last_run" in data
    assert len(data["stations"]) == 3
    assert data["stations"][0]["id"] == "station-paris-2"


def test_api_history(client):
    response = client.get("/api/history/station-paris-1")
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["available"] == 2
    assert data[0]["total"] == 2


def test_api_hourly_stats(client):
    response = client.get("/api/hourly_stats/station-paris-1")
    assert response.status_code == 200
    data = response.get_json()
    assert "hours" in data
    assert "availability_pct" in data
    assert len(data["hours"]) == 24
    assert len(data["availability_pct"]) == 24


def test_api_logs(client):
    response = client.get("/api/logs")
    assert response.status_code == 200
    data = response.get_json()
    assert "errors" in data
    assert "stats" in data


def test_api_logs_clear(client):
    # Ajouter une erreur de test
    from ev_monitor import storage
    storage.log_error("test", "error", "message de test")

    response = client.get("/api/logs")
    assert response.status_code == 200
    assert len(response.get_json()["errors"]) == 1

    response = client.post("/api/logs/clear")
    assert response.status_code == 200
    assert response.get_json() == {"ok": True}

    response = client.get("/api/logs")
    assert len(response.get_json()["errors"]) == 0

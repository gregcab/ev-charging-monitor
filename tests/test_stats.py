"""Tests des statistiques de fiabilité et de la heatmap."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from ev_monitor import storage


def _insert_log(db_path, station_id, timestamp, available, occupied=0, oos=0, unknown=0, total=2):
    """Insère une ligne d’historique avec un timestamp explicite."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO availability_log (station_id, timestamp, available, occupied,
                                          reserved, unknown, out_of_service, total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (station_id, timestamp.isoformat(), available, occupied, 0, unknown, oos, total),
        )
        conn.commit()
    finally:
        conn.close()


def test_get_station_stats_empty(test_paths, monkeypatch, sample_stations):
    monkeypatch.setattr(storage, "DB_PATH", test_paths["db_path"])
    monkeypatch.setattr(storage, "STATIONS_FILE", test_paths["stations_file"])

    with open(test_paths["stations_file"], "w", encoding="utf-8") as f:
        json.dump(sample_stations, f)

    storage.init_db()
    storage.seed_stations()

    stats = storage.get_station_stats("station-aix-1", hours=24)
    assert stats["station_id"] == "station-aix-1"
    assert stats["total_measurements"] == 0
    assert stats["avg_availability_pct"] is None


def test_get_station_stats_computes_average(test_paths, monkeypatch, sample_stations):
    monkeypatch.setattr(storage, "DB_PATH", test_paths["db_path"])
    monkeypatch.setattr(storage, "STATIONS_FILE", test_paths["stations_file"])

    with open(test_paths["stations_file"], "w", encoding="utf-8") as f:
        json.dump(sample_stations, f)

    storage.init_db()
    storage.seed_stations()

    now = datetime.now(timezone.utc)
    _insert_log(test_paths["db_path"], "station-aix-1", now, available=2, total=2)
    _insert_log(test_paths["db_path"], "station-aix-1", now - timedelta(minutes=5), available=1, total=2)
    _insert_log(test_paths["db_path"], "station-aix-1", now - timedelta(minutes=10), available=0, total=2)

    stats = storage.get_station_stats("station-aix-1", hours=24)
    assert stats["total_measurements"] == 3
    assert stats["avg_availability_pct"] == 50.0
    assert stats["zero_availability_count"] == 1
    assert stats["zero_availability_pct"] == pytest.approx(33.3, abs=0.1)


def test_get_station_stats_best_worst_hour(test_paths, monkeypatch, sample_stations):
    monkeypatch.setattr(storage, "DB_PATH", test_paths["db_path"])
    monkeypatch.setattr(storage, "STATIONS_FILE", test_paths["stations_file"])

    with open(test_paths["stations_file"], "w", encoding="utf-8") as f:
        json.dump(sample_stations, f)

    storage.init_db()
    storage.seed_stations()

    now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    _insert_log(test_paths["db_path"], "station-aix-1", now.replace(hour=3), available=2, total=2)
    _insert_log(test_paths["db_path"], "station-aix-1", now.replace(hour=15), available=0, total=2)

    stats = storage.get_station_stats("station-aix-1", hours=24)
    assert stats["best_hour"] == 3
    assert stats["worst_hour"] == 15


def test_get_all_stations_stats(test_paths, monkeypatch, sample_stations):
    monkeypatch.setattr(storage, "DB_PATH", test_paths["db_path"])
    monkeypatch.setattr(storage, "STATIONS_FILE", test_paths["stations_file"])

    with open(test_paths["stations_file"], "w", encoding="utf-8") as f:
        json.dump(sample_stations, f)

    storage.init_db()
    storage.seed_stations()

    now = datetime.now(timezone.utc)
    _insert_log(test_paths["db_path"], "station-aix-1", now, available=2, total=2)

    stats = storage.get_all_stations_stats(hours=24)
    assert len(stats) == 3
    by_id = {s["station_id"]: s for s in stats}
    assert by_id["station-aix-1"]["avg_availability_pct"] == 100.0
    assert by_id["station-aix-2"]["total_measurements"] == 0


def test_get_hourly_heatmap_empty(test_paths, monkeypatch, sample_stations):
    monkeypatch.setattr(storage, "DB_PATH", test_paths["db_path"])
    monkeypatch.setattr(storage, "STATIONS_FILE", test_paths["stations_file"])

    with open(test_paths["stations_file"], "w", encoding="utf-8") as f:
        json.dump(sample_stations, f)

    storage.init_db()
    storage.seed_stations()

    heatmap = storage.get_hourly_heatmap("station-aix-1", days=30)
    assert heatmap["days"] == ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    assert len(heatmap["matrix"]) == 7
    assert all(v is None for row in heatmap["matrix"] for v in row)


def test_get_hourly_heatmap_computes_matrix(test_paths, monkeypatch, sample_stations):
    monkeypatch.setattr(storage, "DB_PATH", test_paths["db_path"])
    monkeypatch.setattr(storage, "STATIONS_FILE", test_paths["stations_file"])

    with open(test_paths["stations_file"], "w", encoding="utf-8") as f:
        json.dump(sample_stations, f)

    storage.init_db()
    storage.seed_stations()

    # Lundi 14h : une mesure à 50%, une à 100% -> moyenne 75%
    monday_14 = datetime(2026, 8, 24, 14, 0, 0, tzinfo=timezone.utc)  # 24/08/2026 = lundi
    _insert_log(test_paths["db_path"], "station-aix-1", monday_14, available=1, total=2)
    _insert_log(test_paths["db_path"], "station-aix-1", monday_14 + timedelta(days=7), available=2, total=2)

    heatmap = storage.get_hourly_heatmap("station-aix-1", days=30)
    assert heatmap["matrix"][0][14] == 75.0  # lundi, 14h


def test_api_station_stats(client):
    response = client.get("/api/stats/station-aix-1")
    assert response.status_code == 200
    data = response.get_json()
    assert data["station_id"] == "station-aix-1"
    assert "avg_availability_pct" in data


def test_api_stations_stats(client):
    response = client.get("/api/stations/stats?hours=24")
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    assert len(data) == 3


def test_api_heatmap(client):
    response = client.get("/api/heatmap/station-aix-1")
    assert response.status_code == 200
    data = response.get_json()
    assert "days" in data
    assert "hours" in data
    assert "matrix" in data
    assert len(data["matrix"]) == 7
    assert len(data["matrix"][0]) == 24

"""Tests unitaires de la couche SQLite."""

import json

import pytest

from ev_monitor import storage


def test_init_db_creates_tables(test_paths, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", test_paths["db_path"])
    monkeypatch.setattr(storage, "STATIONS_FILE", test_paths["stations_file"])
    with open(test_paths["stations_file"], "w", encoding="utf-8") as f:
        json.dump([], f)
    storage.init_db()
    stations = storage.get_all_stations()
    assert stations == []


def test_seed_and_get_all(test_paths, monkeypatch, sample_stations):
    monkeypatch.setattr(storage, "DB_PATH", test_paths["db_path"])
    monkeypatch.setattr(storage, "STATIONS_FILE", test_paths["stations_file"])

    with open(test_paths["stations_file"], "w", encoding="utf-8") as f:
        json.dump(sample_stations, f)

    storage.init_db()
    storage.seed_stations()
    stations = storage.get_all_stations()
    assert len(stations) == 3
    ids = {s["id"] for s in stations}
    assert ids == {s["id"] for s in sample_stations}


def test_save_and_get_latest_availability(test_paths, monkeypatch, sample_stations):
    monkeypatch.setattr(storage, "DB_PATH", test_paths["db_path"])
    monkeypatch.setattr(storage, "STATIONS_FILE", test_paths["stations_file"])

    with open(test_paths["stations_file"], "w", encoding="utf-8") as f:
        json.dump(sample_stations, f)

    storage.init_db()
    storage.seed_stations()
    storage.save_availability(
        "station-paris-1",
        {"available": 1, "occupied": 1, "reserved": 0, "unknown": 0, "outOfService": 0},
        2,
    )
    latest = storage.get_latest_availability("station-paris-1")
    assert latest["available"] == 1
    assert latest["occupied"] == 1
    assert latest["total"] == 2


def test_get_history_filters_hours(test_paths, monkeypatch, sample_stations):
    monkeypatch.setattr(storage, "DB_PATH", test_paths["db_path"])
    monkeypatch.setattr(storage, "STATIONS_FILE", test_paths["stations_file"])

    with open(test_paths["stations_file"], "w", encoding="utf-8") as f:
        json.dump(sample_stations, f)

    storage.init_db()
    storage.seed_stations()

    # Log récent (doit être inclus dans les dernières 24h).
    storage.save_availability(
        "station-paris-1",
        {"available": 2, "occupied": 0, "reserved": 0, "unknown": 0, "outOfService": 0},
        2,
    )

    # Log vieux de plus de 2h inséré directement en base.
    import sqlite3
    from datetime import datetime, timedelta, timezone

    old_ts = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    conn = sqlite3.connect(test_paths["db_path"])
    try:
        conn.execute(
            """
            INSERT INTO availability_log (station_id, timestamp, available, occupied,
                                          reserved, unknown, out_of_service, total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("station-paris-1", old_ts, 0, 0, 0, 0, 0, 2),
        )
        conn.commit()
    finally:
        conn.close()

    history = storage.get_history("station-paris-1", hours=24)
    assert len(history) == 2
    history = storage.get_history("station-paris-1", hours=1)
    assert len(history) == 1
    assert history[0]["available"] == 2


def test_update_station(test_paths, monkeypatch, sample_stations):
    monkeypatch.setattr(storage, "DB_PATH", test_paths["db_path"])
    monkeypatch.setattr(storage, "STATIONS_FILE", test_paths["stations_file"])

    with open(test_paths["stations_file"], "w", encoding="utf-8") as f:
        json.dump(sample_stations, f)

    storage.init_db()
    storage.seed_stations()

    storage.update_station(
        "station-paris-1",
        {"name": "Nouveau nom", "operator": "Nouvel opérateur", "display_order": 42},
    )

    stations = {s["id"]: s for s in storage.load_stations_from_json()}
    assert stations["station-paris-1"]["name"] == "Nouveau nom"
    assert stations["station-paris-1"]["operator"] == "Nouvel opérateur"
    assert stations["station-paris-1"]["display_order"] == 42


def test_update_station_unknown(test_paths, monkeypatch, sample_stations):
    monkeypatch.setattr(storage, "DB_PATH", test_paths["db_path"])
    monkeypatch.setattr(storage, "STATIONS_FILE", test_paths["stations_file"])

    with open(test_paths["stations_file"], "w", encoding="utf-8") as f:
        json.dump(sample_stations, f)

    storage.init_db()
    storage.seed_stations()

    with pytest.raises(ValueError):
        storage.update_station("inexistant", {"name": "Test"})


def test_seed_stations_enriched_columns(test_paths, monkeypatch, sample_stations):
    """Les colonnes enrichies (puissance, logo, services, etc.) sont persistées."""
    monkeypatch.setattr(storage, "DB_PATH", test_paths["db_path"])
    monkeypatch.setattr(storage, "STATIONS_FILE", test_paths["stations_file"])

    with open(test_paths["stations_file"], "w", encoding="utf-8") as f:
        json.dump(sample_stations, f)

    storage.init_db()
    storage.seed_stations()

    stations = {s["id"]: s for s in storage.get_all_stations()}
    paris_1 = stations["station-paris-1"]
    assert paris_1["max_power"] == 50
    assert paris_1["operator_logo_url"] == "https://example.com/opA.png"
    assert paris_1["amenities"] == ["restroom", "restoration"]
    assert paris_1["always_open"] == 1  # stocké en INTEGER
    assert paris_1["is_free"] == 0
    assert paris_1["parking_free"] == 1


def test_save_availability_detailed_states(test_paths, monkeypatch, sample_stations):
    """Les états détaillés (busy, unavailable, out_of_order) sont historisés."""
    monkeypatch.setattr(storage, "DB_PATH", test_paths["db_path"])
    monkeypatch.setattr(storage, "STATIONS_FILE", test_paths["stations_file"])

    with open(test_paths["stations_file"], "w", encoding="utf-8") as f:
        json.dump(sample_stations, f)

    storage.init_db()
    storage.seed_stations()

    storage.save_availability(
        "station-paris-1",
        {
            "available": 0,
            "busy": 1,
            "unavailable": 2,
            "reserved": 0,
            "unknown": 0,
            "outOfOrder": 3,
        },
        6,
    )

    latest = storage.get_latest_availability("station-paris-1")
    assert latest["available"] == 0
    assert latest["busy"] == 1
    assert latest["unavailable"] == 2
    assert latest["occupied"] == 3  # agrégat conservé
    assert latest["out_of_order"] == 3
    assert latest["out_of_service"] == 3  # agrégat conservé
    assert latest["total"] == 6


def test_get_all_stations_parses_amenities_json(test_paths, monkeypatch, sample_stations):
    """Les amenities stockées en JSON dans la base sont re-parsées en liste."""
    monkeypatch.setattr(storage, "DB_PATH", test_paths["db_path"])
    monkeypatch.setattr(storage, "STATIONS_FILE", test_paths["stations_file"])

    with open(test_paths["stations_file"], "w", encoding="utf-8") as f:
        json.dump(sample_stations, f)

    storage.init_db()
    storage.seed_stations()

    stations = storage.get_all_stations()
    paris_1 = next(s for s in stations if s["id"] == "station-paris-1")
    assert paris_1["amenities"] == ["restroom", "restoration"]

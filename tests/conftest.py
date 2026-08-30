import json

import pytest

from ev_monitor import storage
from ev_monitor.dashboard import app


@pytest.fixture
def test_paths(tmp_path):
    """Chemins temporaires pour la base SQLite et le fichier JSON des stations."""
    return {
        "db_path": str(tmp_path / "ev_monitoring.db"),
        "stations_file": str(tmp_path / "stations_validated.json"),
    }


@pytest.fixture
def sample_stations():
    """Jeu de stations factices : un trajet libre et une station sans trajet."""
    return [
        {
            "id": "station-paris-1",
            "name": "Station Paris 1",
            "operator": "OpA",
            "operator_logo_url": "https://example.com/opA.png",
            "address": "Adresse A",
            "direction": "Paris → Lyon",
            "lat": 48.8,
            "lon": 2.7,
            "charging_availability_id": "station-paris-1",
            "chademo_total": 2,
            "connector_type": "CHADEMO",
            "display_order": 1,
            "max_power": 50,
            "amenities": ["restroom", "restoration"],
            "always_open": True,
            "is_free": False,
            "parking_free": True,
            "rating": 4.2,
            "rating_count": 10,
        },
        {
            "id": "station-paris-2",
            "name": "Station Paris 2",
            "operator": "OpB",
            "address": "Adresse B",
            "direction": "Paris → Lyon",
            "lat": 48.8,
            "lon": 2.8,
            "charging_availability_id": "station-paris-2",
            "chademo_total": 1,
            "connector_type": "CHADEMO",
            "display_order": 0,
            "max_power": 50,
        },
        {
            "id": "station-lyon-1",
            "name": "Station Lyon 1",
            "operator": "OpC",
            "address": "Adresse C",
            "direction": None,
            "lat": 48.8,
            "lon": 2.9,
            "charging_availability_id": "station-lyon-1",
            "chademo_total": 4,
            "connector_type": "COMBO_TYPE_2",
            "display_order": 0,
            "max_power": 150,
        },
    ]


@pytest.fixture
def seeded_db(monkeypatch, test_paths, sample_stations):
    """Initialise la base SQLite temporaire avec les stations et quelques logs."""
    monkeypatch.setattr(storage, "DB_PATH", test_paths["db_path"])
    monkeypatch.setattr(storage, "STATIONS_FILE", test_paths["stations_file"])

    with open(test_paths["stations_file"], "w", encoding="utf-8") as f:
        json.dump(sample_stations, f, indent=2)

    storage.init_db()
    storage.seed_stations()

    storage.save_availability(
        "station-paris-1",
        {"available": 2, "occupied": 0, "reserved": 0, "unknown": 0, "outOfService": 0},
        2,
    )
    storage.save_availability(
        "station-paris-2",
        {"available": 0, "occupied": 1, "reserved": 0, "unknown": 0, "outOfService": 0},
        1,
    )
    storage.save_availability(
        "station-lyon-1",
        {"available": 4, "occupied": 0, "reserved": 0, "unknown": 0, "outOfService": 0},
        4,
    )

    storage.save_collect_run("ok", 0, len(sample_stations))

    yield

    # Nettoyage des fichiers temporaires.
    import os

    for path in (test_paths["db_path"], test_paths["stations_file"]):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


@pytest.fixture
def client(seeded_db):
    """Client de test Flask configuré avec l'environnement de test."""
    app.testing = True
    with app.test_client() as test_client:
        yield test_client

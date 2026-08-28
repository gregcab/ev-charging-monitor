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
    """Jeu de stations factices couvrant les deux sens et plusieurs connecteurs."""
    return [
        {
            "id": "station-aix-1",
            "name": "Station Aix 1",
            "operator": "OpA",
            "address": "Adresse A",
            "direction": "Aix → Nice",
            "lat": 43.5,
            "lon": 5.9,
            "charging_availability_id": "station-aix-1",
            "chademo_total": 2,
            "connector_type": "CHADEMO",
            "display_order": 1,
        },
        {
            "id": "station-aix-2",
            "name": "Station Aix 2",
            "operator": "OpB",
            "address": "Adresse B",
            "direction": "Aix → Nice",
            "lat": 43.5,
            "lon": 6.0,
            "charging_availability_id": "station-aix-2",
            "chademo_total": 1,
            "connector_type": "CHADEMO",
            "display_order": 0,
        },
        {
            "id": "station-nice-1",
            "name": "Station Nice 1",
            "operator": "OpC",
            "address": "Adresse C",
            "direction": "Nice → Aix",
            "lat": 43.5,
            "lon": 6.1,
            "charging_availability_id": "station-nice-1",
            "chademo_total": 4,
            "connector_type": "COMBO_TYPE_2",
            "display_order": 0,
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
        "station-aix-1",
        {"available": 2, "occupied": 0, "reserved": 0, "unknown": 0, "outOfService": 0},
        2,
    )
    storage.save_availability(
        "station-aix-2",
        {"available": 0, "occupied": 1, "reserved": 0, "unknown": 0, "outOfService": 0},
        1,
    )
    storage.save_availability(
        "station-nice-1",
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

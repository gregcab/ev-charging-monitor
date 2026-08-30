"""Tests end-to-end avec Playwright.

Ces tests lancent le serveur Flask dans un thread avec une base temporaire
et vérifient les parcours utilisateur critiques dans un navigateur réel.

Ils sont lancés séparément : pytest -m e2e
"""

import json
import threading
import time

import pytest
from werkzeug.serving import make_server

from ev_monitor import storage
from ev_monitor.dashboard import app


class ServerThread(threading.Thread):
    """Serveur Flask lancé dans un thread pour les tests E2E."""

    def __init__(self, flask_app, port):
        super().__init__(daemon=True)
        self.server = make_server("127.0.0.1", port, flask_app)
        self.ctx = flask_app.app_context()
        self.ctx.push()

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    """Démarre un serveur Flask avec une base SQLite temporaire."""
    tmp_path = tmp_path_factory.mktemp("e2e")
    db_path = str(tmp_path / "ev_monitoring.db")
    stations_file = str(tmp_path / "stations_validated.json")

    old_db_path = storage.DB_PATH
    old_stations_file = storage.STATIONS_FILE

    storage.DB_PATH = db_path
    storage.STATIONS_FILE = stations_file

    sample_stations = [
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
    ]

    with open(stations_file, "w", encoding="utf-8") as f:
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

    port = 5001
    server = ServerThread(app, port)
    server.start()
    time.sleep(0.5)

    yield f"http://127.0.0.1:{port}"

    server.shutdown()
    server.join()

    storage.DB_PATH = old_db_path
    storage.STATIONS_FILE = old_stations_file


@pytest.mark.e2e
def test_homepage_loads(live_server, page):
    """La page d'accueil se charge et affiche les stations."""
    page.goto(live_server + "/")
    assert "EV Charging Monitor" in page.title()
    assert page.locator("h1").first.text_content() == "EV Charging Monitor"
    assert page.locator("#stationsTable").get_by_text("Station Paris 1").is_visible()
    assert page.locator("#stationsTable").get_by_text("Station Paris 2").is_visible()
    # Stats
    assert page.get_by_text("Stations", exact=True).is_visible()
    assert page.get_by_text("Bornes suivies", exact=True).is_visible()


@pytest.mark.e2e
def test_filter_modal(live_server, page):
    """Le bouton Filtres ouvre et ferme le modal."""
    page.goto(live_server + "/")
    page.click("text=Filtres")
    assert page.locator("#filterModal").is_visible()
    assert page.locator("#filterPower").is_visible()
    assert page.locator("#filterOperator").is_visible()
    assert page.locator("#filter24h").is_visible()
    page.click("text=Fermer")
    assert not page.locator("#filterModal").is_visible()


@pytest.mark.e2e
def test_station_page(live_server, page):
    """La fiche station se charge avec le header et les graphiques."""
    page.goto(live_server + "/station/station-paris-1")
    assert "Station Paris 1" in page.title()
    assert page.locator("h1").first.text_content() == "Station Paris 1"
    assert page.locator("text=Adresse A").is_visible()
    assert page.locator("#historyChart").is_visible()
    assert page.locator("#hourlyChart").is_visible()
    assert page.locator("#heatmapChart").is_visible()


@pytest.mark.e2e
def test_navigation_links(live_server, page):
    """Les liens de navigation principaux fonctionnent."""
    page.goto(live_server + "/")
    page.click("text=Carte")
    assert "/carte" in page.url
    page.go_back()
    page.click("text=Paramètres")
    assert "/parametres" in page.url
    page.go_back()
    page.click("text=Aide")
    assert "/aide" in page.url
    page.go_back()
    page.click("text=Voir les logs")
    assert "/logs" in page.url


@pytest.mark.e2e
def test_export_csv(live_server, page):
    """Le lien d'export CSV retourne un fichier text/csv."""
    page.goto(live_server + "/station/station-paris-1")
    with page.expect_download() as download_info:
        page.click("text=Exporter CSV")
    download = download_info.value
    assert download.suggested_filename.endswith(".csv")


@pytest.mark.e2e
def test_mobile_cards_visible_on_small_viewport(live_server, page):
    """Les cartes mobile sont visibles sous 900 px."""
    page.set_viewport_size({"width": 500, "height": 800})
    page.goto(live_server + "/")
    assert page.locator(".mobile-cards").is_visible()
    assert page.locator(".station-card").first.is_visible()
    # Le tableau est masqué
    assert not page.locator("#stationsTable").is_visible()

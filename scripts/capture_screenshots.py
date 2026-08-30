#!/usr/bin/env python3
"""Génère des captures d'écran du dashboard pour le README GitHub.

Lance l'application Flask sur un port temporaire avec des données factices
(30 jours d'historique) et capture les pages principales.
"""

import json
import os
import random
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Chemin racine du projet
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ev_monitor import config, storage
from ev_monitor.dashboard import app

OUTPUT_DIR = ROOT / "docs" / "screenshots"

SAMPLE_STATIONS = [
    {
        "id": "ionity-aire-de-taponas",
        "name": "IONITY - Aire de Taponas",
        "operator": "IONITY",
        "address": "A6, Aire de Taponas, 69220 Belleville-en-Beaujolais",
        "direction": "Paris → Lyon",
        "lat": 46.1385,
        "lon": 4.7593,
        "charging_availability_id": "ionity-aire-de-taponas",
        "chademo_total": 6,
        "connector_type": "COMBO_TYPE_2",
        "display_order": 0,
    },
    {
        "id": "totalenergies-aire-de-la-coupole",
        "name": "TotalEnergies - Aire de la Coupole",
        "operator": "TotalEnergies",
        "address": "A6, Aire de la Coupole, 71850 Charnay-lès-Mâcon",
        "direction": "Paris → Lyon",
        "lat": 46.2967,
        "lon": 4.8012,
        "charging_availability_id": "totalenergies-aire-de-la-coupole",
        "chademo_total": 2,
        "connector_type": "CHADEMO",
        "display_order": 1,
    },
    {
        "id": "ionity-aire-de-roussillon-ouest",
        "name": "IONITY - Aire de Roussillon Ouest",
        "operator": "IONITY",
        "address": "A7, Aire de Roussillon Ouest, 38150 Roussillon",
        "direction": "Lyon → Marseille",
        "lat": 45.3521,
        "lon": 4.8102,
        "charging_availability_id": "ionity-aire-de-roussillon-ouest",
        "chademo_total": 6,
        "connector_type": "COMBO_TYPE_2",
        "display_order": 0,
    },
    {
        "id": "totalenergies-aire-de-mornas",
        "name": "TotalEnergies - Aire de Mornas",
        "operator": "TotalEnergies",
        "address": "A7, Aire de Mornas, 84550 Mornas",
        "direction": "Lyon → Marseille",
        "lat": 44.2089,
        "lon": 4.7314,
        "charging_availability_id": "totalenergies-aire-de-mornas",
        "chademo_total": 2,
        "connector_type": "CHADEMO",
        "display_order": 1,
    },
    {
        "id": "electra-paris-15e-convention",
        "name": "Electra - Paris 15e Convention",
        "operator": "Electra",
        "address": "Rue de la Convention, 75015 Paris",
        "direction": "Trajet boulot",
        "lat": 48.8421,
        "lon": 2.3156,
        "charging_availability_id": "electra-paris-15e-convention",
        "chademo_total": 8,
        "connector_type": "COMBO_TYPE_2",
        "display_order": 0,
    },
    {
        "id": "tesla-supercharger-velizy",
        "name": "Tesla Supercharger - Vélizy 2",
        "operator": "Tesla",
        "address": "Centre commercial Vélizy 2, 78140 Vélizy-Villacoublay",
        "direction": "Trajet boulot",
        "lat": 48.7798,
        "lon": 2.2214,
        "charging_availability_id": "tesla-supercharger-velizy",
        "chademo_total": 12,
        "connector_type": "TESLA_SUPERCHARGER_EU",
        "display_order": 1,
    },
]


def _setup_test_data(tmp_dir):
    """Crée une base SQLite temporaire avec 30 jours d'historique."""
    # Met à jour les chemins dans le module storage (import par valeur)
    storage.DB_PATH = str(tmp_dir / "ev_monitoring.db")
    storage.STATIONS_FILE = str(tmp_dir / "stations_validated.json")
    config.DB_PATH = storage.DB_PATH
    config.STATIONS_FILE = storage.STATIONS_FILE

    with open(config.STATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(SAMPLE_STATIONS, f, indent=2)

    storage.init_db()
    storage.seed_stations()

    # Génère 30 jours d'historique, mesure toutes les 5 minutes
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    interval = timedelta(minutes=5)
    current = start

    random.seed(42)
    total_inserted = 0
    while current <= end:
        for station in SAMPLE_STATIONS:
            total = station["chademo_total"]
            hour = current.hour
            # Simuler une disponibilité plus forte la nuit (22h-6h) et plus faible la journée
            base_prob = 0.75 if 22 <= hour or hour < 6 else 0.45
            # Ajouter une variation aléatoire par station
            station_factor = 1.0 + (hash(station["id"]) % 5 - 2) * 0.05
            prob = min(0.95, max(0.1, base_prob * station_factor))
            available = sum(1 for _ in range(total) if random.random() < prob)
            occupied = total - available if random.random() < 0.8 else 0
            oos = total - available - occupied if random.random() < 0.1 else 0
            unknown = total - available - occupied - oos

            # Insertion directe en base avec le timestamp souhaité
            import sqlite3

            conn = sqlite3.connect(config.DB_PATH)
            try:
                conn.execute(
                    """
                    INSERT INTO availability_log (station_id, timestamp, available, occupied,
                                                  reserved, unknown, out_of_service, total)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        station["id"],
                        current.isoformat(),
                        available,
                        max(0, occupied),
                        0,
                        max(0, unknown),
                        max(0, oos),
                        total,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
            total_inserted += 1
        current += interval

    storage.save_collect_run("ok", 0, len(SAMPLE_STATIONS))
    print(f"{total_inserted} mesures générées.")


def _start_server(port):
    """Lance le serveur Flask dans un thread daemon."""
    app.testing = False
    thread = threading.Thread(target=lambda: app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False), daemon=True)
    thread.start()


def _wait_for_server(port, timeout=30):
    """Attend que le serveur réponde."""
    import urllib.request

    url = f"http://127.0.0.1:{port}/"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("Le serveur Flask n'a pas démarré à temps")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    tmp_dir = Path(tempfile.mkdtemp(prefix="ev_monitor_screenshots_"))
    try:
        _setup_test_data(tmp_dir)
        port = 8765
        _start_server(port)
        _wait_for_server(port)

        from playwright.sync_api import sync_playwright

        base_url = f"http://127.0.0.1:{port}"

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1200})

            # Capture du dashboard (page complète pour montrer tableau + fiabilité)
            page.goto(base_url + "/")
            page.wait_for_selector("#reliabilityBody", timeout=10000)
            # Attendre que le JavaScript remplisse le tableau
            time.sleep(1)
            page.screenshot(path=str(OUTPUT_DIR / "dashboard.png"), full_page=True)
            print(f"Capture : {OUTPUT_DIR / 'dashboard.png'}")

            # Capture de la section fiabilité du dashboard
            reliability_card = page.locator(".reliability-card")
            reliability_card.wait_for(timeout=10000)
            reliability_card.screenshot(path=str(OUTPUT_DIR / "reliability.png"))
            print(f"Capture : {OUTPUT_DIR / 'reliability.png'}")

            # Capture de la page de détail
            page.goto(base_url + "/station/ionity-aire-de-taponas")
            page.wait_for_selector("#historyChart", timeout=10000)
            time.sleep(1)
            page.screenshot(path=str(OUTPUT_DIR / "station-detail.png"), full_page=True)
            print(f"Capture : {OUTPUT_DIR / 'station-detail.png'}")

            # Capture de la heatmap
            heatmap_card = page.locator("#heatmapCard")
            heatmap_card.wait_for(timeout=10000)
            heatmap_card.screenshot(path=str(OUTPUT_DIR / "heatmap.png"))
            print(f"Capture : {OUTPUT_DIR / 'heatmap.png'}")

            # Capture de la carte interactive (Leaflet + tuiles OSM via CDN)
            page.goto(base_url + "/carte")
            page.wait_for_selector("#map", timeout=10000)
            # Attendre les marqueurs (circleMarker = SVG) puis les tuiles OSM
            page.wait_for_selector(".leaflet-overlay-pane path", timeout=15000)
            time.sleep(3)
            page.screenshot(path=str(OUTPUT_DIR / "carte.png"))
            print(f"Capture : {OUTPUT_DIR / 'carte.png'}")

            # Capture de la page des paramètres
            page.goto(base_url + "/parametres")
            page.wait_for_selector("#prefAppName", timeout=10000)
            time.sleep(1)
            page.screenshot(path=str(OUTPUT_DIR / "parametres.png"), full_page=True)
            print(f"Capture : {OUTPUT_DIR / 'parametres.png'}")

            browser.close()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()

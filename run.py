#!/usr/bin/env python3
"""Point d'entrée : initialise la base, lance le monitoring et le dashboard."""

import logging
import shutil
import threading
from pathlib import Path

from ev_monitor.config import (
    BASE_DIR,
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    MONITOR_INTERVAL_MINUTES,
    STATIONS_FILE,
)
from ev_monitor.dashboard import app
from ev_monitor.monitor import run_scheduler
from ev_monitor.storage import init_db, seed_stations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def _copy_default_stations_file():
    """Copie le fichier de stations par défaut vers le chemin persistant s'il n'existe pas.

    Cela garantit qu'un premier démarrage en Docker dispose des stations par défaut
    tout en permettant au volume persistant de conserver les modifications ultérieures.
    """
    stations_path = Path(STATIONS_FILE)
    if stations_path.exists():
        return
    default_path = Path(BASE_DIR) / "stations_validated.json"
    if default_path.exists():
        stations_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(default_path, stations_path)
        logging.info("Fichier de stations par défaut copié vers %s", stations_path)


def main():
    _copy_default_stations_file()
    init_db()
    seed_stations()

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    logging.info("Dashboard disponible sur http://%s:%d", DASHBOARD_HOST, DASHBOARD_PORT)
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()

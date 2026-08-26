#!/usr/bin/env python3
"""Point d'entrée : initialise la base, lance le monitoring et le dashboard."""

import logging
import threading

from ev_monitor.config import DASHBOARD_HOST, DASHBOARD_PORT, MONITOR_INTERVAL_MINUTES
from ev_monitor.dashboard import app
from ev_monitor.monitor import run_scheduler
from ev_monitor.storage import init_db, seed_stations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main():
    init_db()
    seed_stations()

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    logging.info("Dashboard disponible sur http://%s:%d", DASHBOARD_HOST, DASHBOARD_PORT)
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()

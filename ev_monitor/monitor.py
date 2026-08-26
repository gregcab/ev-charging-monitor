import logging
import time

import schedule

from ev_monitor.config import MONITOR_INTERVAL_MINUTES
from ev_monitor.storage import get_all_stations, save_availability
from ev_monitor.tomtom_client import get_charging_availability

logger = logging.getLogger(__name__)


def collect_once():
    stations = get_all_stations()
    logger.info("Démarrage d’un cycle de collecte pour %d station(s)", len(stations))

    for station in stations:
        station_id = station["id"]
        avail_id = station["charging_availability_id"]

        try:
            chademo = get_charging_availability(avail_id)
        except Exception as exc:
            logger.warning("Erreur pour %s (%s) : %s", station["name"], station_id, exc)
            continue

        if chademo is None:
            logger.info("Pas de données Chademo pour %s (%s)", station["name"], station_id)
            continue

        current = chademo.get("availability", {}).get("current", {})
        total = chademo.get("total", 0)
        save_availability(station_id, current, total)
        logger.info(
            "%s | Chademo %d/%d dispo (occupés=%d, hors service=%d)",
            station["name"],
            current.get("available", 0),
            total,
            current.get("occupied", 0),
            current.get("outOfService", 0),
        )

    logger.info("Cycle de collecte terminé.")


def run_scheduler():
    logger.info("Planification toutes les %d minutes", MONITOR_INTERVAL_MINUTES)
    schedule.every(MONITOR_INTERVAL_MINUTES).minutes.do(collect_once)
    collect_once()
    while True:
        schedule.run_pending()
        time.sleep(1)

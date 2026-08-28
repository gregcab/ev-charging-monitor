import logging
import time

import schedule

from ev_monitor.config import MONITOR_INTERVAL_MINUTES
from ev_monitor.storage import (
    get_all_stations,
    log_error,
    save_availability,
    save_collect_run,
)
from ev_monitor.chargemap_client import get_charging_availability

logger = logging.getLogger(__name__)


def collect_once():
    stations = get_all_stations()
    station_count = len(stations)
    error_count = 0
    logger.info("Démarrage d’un cycle de collecte pour %d station(s)", station_count)

    for station in stations:
        station_id = station["id"]
        avail_id = station["charging_availability_id"]

        try:
            chademo = get_charging_availability(avail_id)
        except Exception as exc:
            error_count += 1
            logger.warning("Erreur pour %s (%s) : %s", station["name"], station_id, exc)
            log_error(
                source="tomtom",
                level="error",
                message=f"Erreur de collecte pour {station['name']}",
                station_id=station_id,
                details=str(exc),
            )
            continue

        if chademo is None:
            logger.info("Pas de données Chademo pour %s (%s)", station["name"], station_id)
            log_error(
                source="tomtom",
                level="warning",
                message=f"Aucun connecteur Chademo trouvé pour {station['name']}",
                station_id=station_id,
            )
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

    if error_count == 0:
        status = "ok"
    elif error_count < station_count:
        status = "partial"
    else:
        status = "error"
    save_collect_run(status=status, error_count=error_count, station_count=station_count)
    logger.info("Cycle de collecte terminé (%s, %d erreur(s)).", status, error_count)


def run_scheduler():
    logger.info("Planification toutes les %d minutes", MONITOR_INTERVAL_MINUTES)
    schedule.every(MONITOR_INTERVAL_MINUTES).minutes.do(collect_once)
    collect_once()
    while True:
        schedule.run_pending()
        time.sleep(1)

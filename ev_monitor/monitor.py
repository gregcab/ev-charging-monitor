import logging
import time

import schedule

from ev_monitor.storage import (
    get_all_stations,
    get_effective_settings,
    log_error,
    save_availability,
    save_collect_run,
)
from ev_monitor.chargemap_client import (
    connector_label,
    get_charging_availability,
)

logger = logging.getLogger(__name__)


def collect_once():
    stations = get_all_stations()
    station_count = len(stations)
    error_count = 0
    default_connector_type = get_effective_settings()["default_connector_type"]
    logger.info("Démarrage d’un cycle de collecte pour %d station(s)", station_count)

    for station in stations:
        station_id = station["id"]
        avail_id = station["charging_availability_id"]
        connector_type = station.get("connector_type") or default_connector_type
        label = connector_label(connector_type)

        try:
            availability = get_charging_availability(avail_id, connector_type)
        except Exception as exc:
            error_count += 1
            logger.warning("Erreur pour %s (%s) : %s", station["name"], station_id, exc)
            log_error(
                source="chargemap",
                level="error",
                message=f"Erreur de collecte pour {station['name']}",
                station_id=station_id,
                details=str(exc),
            )
            continue

        if availability is None:
            logger.info("Pas de données %s pour %s (%s)", label, station["name"], station_id)
            log_error(
                source="chargemap",
                level="warning",
                message=f"Aucun connecteur {label} trouvé pour {station['name']}",
                station_id=station_id,
            )
            continue

        current = availability.get("availability", {}).get("current", {})
        total = availability.get("total", 0)
        save_availability(station_id, current, total)
        logger.info(
            "%s | %s %d/%d dispo (occupés=%d, hors service=%d)",
            station["name"],
            label,
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
    interval = get_effective_settings()["monitor_interval_minutes"]
    logger.info("Planification toutes les %d minutes", interval)
    schedule.every(interval).minutes.do(collect_once)
    collect_once()
    while True:
        # Relit l'intervalle effectif à chaque itération : replanifie si modifié
        # dans les paramètres (base > env > défaut).
        new_interval = get_effective_settings()["monitor_interval_minutes"]
        if new_interval != interval:
            logger.info(
                "Intervalle de collecte modifié : %d → %d minutes", interval, new_interval
            )
            schedule.clear()
            schedule.every(new_interval).minutes.do(collect_once)
            interval = new_interval
        schedule.run_pending()
        time.sleep(1)

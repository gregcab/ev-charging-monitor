import logging
import random
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

# Compteur d'erreurs consécutives par station (réinitialisé au succès).
_consecutive_errors = {}
# Nombre de cycles complets en erreur (toutes les stations en échec).
_full_error_cycles = 0


def _jittered_interval(base_minutes):
    """Retourne un intervalle aléatoire centré sur base_minutes.

    Pour un intervalle de 5 minutes, retourne typiquement entre 4 et 7 minutes
    (± 20 à 40 % de jitter).
    """
    jittered = base_minutes * random.uniform(0.8, 1.4)
    return max(1, round(jittered))


def _request_pause():
    """Pause aléatoire entre deux requêtes pour éviter un pattern robot."""
    time.sleep(random.uniform(2, 5))


def collect_once():
    global _full_error_cycles
    stations = get_all_stations()
    station_count = len(stations)
    error_count = 0
    skipped_count = 0
    default_connector_type = get_effective_settings()["default_connector_type"]
    logger.info("Démarrage d’un cycle de collecte pour %d station(s)", station_count)

    for index, station in enumerate(stations):
        station_id = station["id"]
        avail_id = station["charging_availability_id"]
        connector_type = station.get("connector_type") or default_connector_type
        label = connector_label(connector_type)

        # Backoff : si 3 erreurs consécutives sur cette station, sauter ce cycle.
        consecutive = _consecutive_errors.get(station_id, 0)
        if consecutive >= 3:
            skipped_count += 1
            logger.info(
                "Backoff : %s (%s) ignoré après %d erreurs consécutives",
                station["name"],
                station_id,
                consecutive,
            )
            continue

        # Espacer les requêtes pour ne pas envoyer une rafale à intervalle fixe.
        if index > 0:
            _request_pause()

        try:
            availability = get_charging_availability(avail_id, connector_type)
        except Exception as exc:
            error_count += 1
            _consecutive_errors[station_id] = consecutive + 1
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

        _consecutive_errors[station_id] = 0
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

    if error_count == 0 and skipped_count == 0:
        status = "ok"
        _full_error_cycles = 0
    elif error_count < station_count:
        status = "partial"
        _full_error_cycles = 0
    else:
        status = "error"
        _full_error_cycles += 1

    save_collect_run(status=status, error_count=error_count, station_count=station_count)
    logger.info(
        "Cycle de collecte terminé (%s, %d erreur(s), %d ignoré(s)).",
        status,
        error_count,
        skipped_count,
    )


def run_scheduler():
    base_interval = get_effective_settings()["monitor_interval_minutes"]

    def schedule_next():
        interval = _jittered_interval(base_interval)
        if _full_error_cycles >= 2:
            interval *= 2
            logger.warning(
                "Backoff global : %d cycles complets en erreur, intervalle doublé à %d min",
                _full_error_cycles,
                interval,
            )
        schedule.every(interval).minutes.do(collect_and_reschedule)
        logger.info("Prochaine collecte dans ~%d minutes", interval)

    def collect_and_reschedule():
        collect_once()
        schedule_next()
        return schedule.CancelJob

    schedule_next()
    collect_once()

    while True:
        # Relit l'intervalle effectif à chaque itération : replanifie si modifié
        # dans les paramètres (base > env > défaut).
        new_base = get_effective_settings()["monitor_interval_minutes"]
        if new_base != base_interval:
            logger.info(
                "Intervalle de collecte modifié : %d → %d minutes", base_interval, new_base
            )
            base_interval = new_base
            schedule.clear()
            schedule_next()
        schedule.run_pending()
        time.sleep(1)

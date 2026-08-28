import logging
from datetime import datetime, timezone

import pytz
from flask import Flask, jsonify, render_template, request

from ev_monitor.chargemap_client import (
    connector_label,
    extract_slug,
    get_station_info,
    search_stations,
)
from ev_monitor.config import MONITOR_INTERVAL_MINUTES
from ev_monitor.storage import (
    add_station,
    clear_errors,
    get_all_stations,
    get_error_stats,
    get_history,
    get_last_collect_run,
    get_last_zero_availability,
    get_latest_availability,
    get_recent_errors,
)

logger = logging.getLogger(__name__)
app = Flask(__name__)

PARIS_TZ = pytz.timezone("Europe/Paris")


@app.template_filter("fr_datetime")
def fr_datetime(value, fmt="%d/%m %H:%M"):
    if not value:
        return value
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(PARIS_TZ).strftime(fmt)


@app.template_filter("connector_label")
def connector_label_filter(value):
    return connector_label(value or "CHADEMO")


def _enrich_station(station, include_history=False):
    station = dict(station)
    latest = get_latest_availability(station["id"])
    if latest:
        station["latest"] = latest
    if include_history:
        station["history"] = get_history(station["id"], hours=24)
        last_zero = get_last_zero_availability(station["id"])
        station["last_zero"] = last_zero["timestamp"] if last_zero else None
    return station


def _sort_stations(stations):
    """Groupe par sens et ordonne dans le sens de circulation."""
    stations.sort(key=lambda s: (
        0 if s.get("direction") == "Aix → Nice" else 1,
        s["lon"] if s.get("direction") == "Aix → Nice" else -s["lon"]
    ))
    return stations


@app.route("/")
def index():
    stations = _sort_stations(
        [_enrich_station(s, include_history=True) for s in get_all_stations()]
    )
    last_run = get_last_collect_run()
    return render_template(
        "index.html",
        stations=stations,
        interval=MONITOR_INTERVAL_MINUTES,
        last_run=last_run,
    )


@app.route("/station/<station_id>")
def station_detail(station_id):
    stations = {s["id"]: s for s in get_all_stations()}
    station = stations.get(station_id)
    if not station:
        return "Station non trouvée", 404
    return render_template("station.html", station=station)


@app.route("/logs")
def logs_page():
    hours = int(request.args.get("hours", "24"))
    level = request.args.get("level") or None
    errors = get_recent_errors(hours=hours, level=level)
    stats = get_error_stats(hours=hours)
    return render_template(
        "logs.html",
        errors=errors,
        hours=hours,
        level=level,
        stats=stats,
    )


@app.route("/api/stations")
def api_stations():
    stations = [_enrich_station(s) for s in get_all_stations()]
    return jsonify(stations)


@app.route("/api/dashboard")
def api_dashboard():
    stations = _sort_stations(
        [_enrich_station(s, include_history=True) for s in get_all_stations()]
    )
    return jsonify({
        "stations": stations,
        "interval": MONITOR_INTERVAL_MINUTES,
        "last_run": get_last_collect_run(),
    })


def _compute_hourly_stats(station_id, hours=720):
    """Calcule le taux moyen de disponibilité par heure de la journée (0-23)."""
    history = get_history(station_id, hours=hours)
    hours_data = {h: [] for h in range(24)}
    for row in history:
        dt = datetime.fromisoformat(row["timestamp"]).astimezone(PARIS_TZ)
        hour = dt.hour
        total = row.get("total") or 1
        hours_data[hour].append(row.get("available", 0) / total)
    return [
        round(sum(values) / len(values) * 100, 1) if values else None
        for hour, values in hours_data.items()
    ]


@app.route("/api/history/<station_id>")
def api_history(station_id):
    hours = int(request.args.get("hours", "24"))
    return jsonify(get_history(station_id, hours=hours))


@app.route("/api/hourly_stats/<station_id>")
def api_hourly_stats(station_id):
    hours = int(request.args.get("hours", "720"))
    return jsonify({
        "hours": list(range(24)),
        "availability_pct": _compute_hourly_stats(station_id, hours=hours),
    })


@app.route("/api/logs")
def api_logs():
    hours = int(request.args.get("hours", "24"))
    level = request.args.get("level") or None
    return jsonify({
        "errors": get_recent_errors(hours=hours, level=level),
        "stats": get_error_stats(hours=hours),
    })


@app.route("/api/logs/clear", methods=["POST"])
def api_logs_clear():
    hours = request.args.get("hours", type=int)
    clear_errors(hours=hours)
    logger.info("Logs effacés (hours=%s)", hours)
    return jsonify({"ok": True})


@app.route("/aide")
def aide_page():
    return render_template("aide.html", interval=MONITOR_INTERVAL_MINUTES)


@app.route("/api/stations/search")
def api_stations_search():
    query = (request.args.get("q") or "").strip()
    if len(query) < 2:
        return jsonify({"error": "Recherche trop courte (2 caractères minimum)"}), 400
    try:
        results = search_stations(query)
        return jsonify({"results": results})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        logger.exception("Erreur lors de la recherche de stations (%s)", query)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stations/add", methods=["POST"])
def api_stations_add():
    data = request.get_json(silent=True) or {}
    direction = data.get("direction") or None
    connector_type = data.get("connector_type") or "CHADEMO"
    try:
        slug = extract_slug(data.get("slug"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        station = get_station_info(slug, connector_type)
        if station["chademo_total"] == 0:
            return jsonify({
                "error": f"Aucun connecteur {connector_label(connector_type)} "
                         f"trouvé pour la station {station.get('name') or slug}"
            }), 400
        if direction:
            station["direction"] = direction
        station.pop("connectors", None)  # info d'affichage, non persistée
        add_station(station)
        return jsonify({"ok": True, "station": station})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Erreur lors de l'ajout de la station %s", slug)
        return jsonify({"error": str(exc)}), 500

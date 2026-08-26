import logging
from datetime import datetime, timezone

import pytz
from flask import Flask, jsonify, render_template, request

from ev_monitor.config import MONITOR_INTERVAL_MINUTES
from ev_monitor.storage import (
    get_all_stations,
    get_history,
    get_last_zero_availability,
    get_latest_availability,
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
    return render_template("index.html", stations=stations, interval=MONITOR_INTERVAL_MINUTES)


@app.route("/station/<station_id>")
def station_detail(station_id):
    stations = {s["id"]: s for s in get_all_stations()}
    station = stations.get(station_id)
    if not station:
        return "Station non trouvée", 404
    return render_template("station.html", station=station)


@app.route("/api/stations")
def api_stations():
    stations = [_enrich_station(s) for s in get_all_stations()]
    return jsonify(stations)


@app.route("/api/dashboard")
def api_dashboard():
    stations = _sort_stations(
        [_enrich_station(s, include_history=True) for s in get_all_stations()]
    )
    return jsonify({"stations": stations, "interval": MONITOR_INTERVAL_MINUTES})


@app.route("/api/history/<station_id>")
def api_history(station_id):
    hours = int(request.args.get("hours", "24"))
    return jsonify(get_history(station_id, hours=hours))

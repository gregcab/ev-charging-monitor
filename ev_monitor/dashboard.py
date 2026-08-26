import logging
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request

from ev_monitor.config import MONITOR_INTERVAL_MINUTES
from ev_monitor.storage import (
    get_all_stations,
    get_history,
    get_latest_availability,
)

logger = logging.getLogger(__name__)
app = Flask(__name__)


def _enrich_station(station, include_history=False):
    station = dict(station)
    latest = get_latest_availability(station["id"])
    if latest:
        station["latest"] = latest
    if include_history:
        station["history"] = get_history(station["id"], hours=24)
    return station


@app.route("/")
def index():
    stations = [_enrich_station(s, include_history=True) for s in get_all_stations()]
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


@app.route("/api/history/<station_id>")
def api_history(station_id):
    hours = int(request.args.get("hours", "24"))
    return jsonify(get_history(station_id, hours=hours))

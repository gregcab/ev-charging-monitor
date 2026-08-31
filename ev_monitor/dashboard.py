import csv
import io
import logging
from datetime import datetime, timezone

import pytz
from flask import Flask, Response, jsonify, render_template, request

from ev_monitor.chargemap_client import (
    CONNECTOR_LABELS,
    connector_label,
    extract_slug,
    get_station_detail,
    get_station_info,
    search_nearby,
    search_stations,
)
from ev_monitor.config import DEFAULT_CONNECTOR_TYPE
from ev_monitor.storage import (
    add_station,
    clear_errors,
    delete_trajet,
    get_all_stations,
    get_all_stations_stats,
    get_effective_settings,
    get_error_stats,
    get_feedback_counts,
    get_history,
    get_hourly_heatmap,
    get_last_collect_run,
    get_last_zero_availability,
    get_latest_availability,
    get_recent_errors,
    get_station_stats,
    get_trajets,
    refresh_station_metadata,
    rename_trajet,
    reset_settings,
    save_settings,
    save_feedbacks,
    search_feedbacks,
    update_station,
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
    return connector_label(value or DEFAULT_CONNECTOR_TYPE)


@app.context_processor
def inject_app_identity():
    """Injecte l'identité de l'app (préférences effectives) dans tous les templates."""
    settings = get_effective_settings()
    return {
        "app_name": settings["app_name"],
        "app_subtitle": settings["app_subtitle"],
        "show_station_details": settings["show_station_details"],
    }


def _enrich_station(station, include_history=False):
    station = dict(station)
    latest = get_latest_availability(station["id"])
    if latest:
        station["latest"] = latest
    if include_history:
        station["history"] = get_history(station["id"], hours=24)
        station["hourly_24h"] = _hourly_availability_24h(station["id"])
        last_zero = get_last_zero_availability(station["id"])
        station["last_zero"] = last_zero["timestamp"] if last_zero else None
    return station


def _avg_availability_pct(station_id, hours=24):
    """Calcule le taux moyen de disponibilité sur les dernières heures."""
    history = get_history(station_id, hours=hours)
    if not history:
        return None
    ratios = [
        (row.get("available") or 0) / (row.get("total") or 1)
        for row in history
    ]
    return round(sum(ratios) / len(ratios) * 100)


def _hourly_availability_24h(station_id):
    """Calcule le taux moyen de disponibilité par heure depuis minuit du jour en cours.

    Retourne une liste de 24 dicts (00h-23h) : hour, pct (None si pas de données),
    css_class, tooltip. Les heures futures du jour courant n'ont pas de données.
    """
    now = datetime.now(PARIS_TZ)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed_hours = int((now - midnight).total_seconds() // 3600) + 1
    history = get_history(station_id, hours=max(elapsed_hours, 1))
    buckets = {h: [] for h in range(24)}
    for row in history:
        dt = datetime.fromisoformat(row["timestamp"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(PARIS_TZ)
        if local_dt.date() != now.date():
            continue
        local_hour = local_dt.hour
        total = row.get("total") or 1
        buckets[local_hour].append((row.get("available") or 0) / total)

    result = []
    for hour in range(24):
        values = buckets[hour]
        if values:
            pct = round(sum(values) / len(values) * 100)
            css_class = "green" if pct >= 70 else ("orange" if pct >= 30 else "red")
            tooltip = f"{hour}h : {pct}% de dispo"
        else:
            pct = None
            css_class = "empty"
            tooltip = f"{hour}h : pas de données"
        result.append({
            "hour": hour,
            "pct": pct,
            "css_class": css_class,
            "tooltip": tooltip,
        })
    return result


def _sort_stations(stations):
    """Trie par trajet (alphabétique, sans trajet à la fin), ordre d'affichage, puis longitude."""
    stations.sort(key=lambda s: (
        0 if s.get("direction") else 1,
        (s.get("direction") or "").lower(),
        s.get("display_order") or 0,
        s.get("lon") or 0,
    ))
    return stations


@app.route("/")
def index():
    settings = get_effective_settings()
    stations = _sort_stations(
        [_enrich_station(s, include_history=True) for s in get_all_stations()]
    )
    last_run = get_last_collect_run()
    return render_template(
        "index.html",
        stations=stations,
        interval=settings["monitor_interval_minutes"],
        last_run=last_run,
        trajets=[t["name"] for t in get_trajets()],
        default_connector_type=settings["default_connector_type"],
    )


@app.route("/station/<station_id>")
def station_detail(station_id):
    stations = {s["id"]: s for s in get_all_stations()}
    station = stations.get(station_id)
    if not station:
        return "Station non trouvée", 404

    station = _enrich_station(station, include_history=True)
    avg_availability_pct = _avg_availability_pct(station_id, hours=24)

    station_detail_data = None
    if get_effective_settings()["show_station_details"]:
        try:
            slug = station.get("charging_availability_id", station_id)
            station_detail_data = get_station_detail(slug, station.get("connector_type"))
        except Exception as exc:
            logger.warning("Impossible de charger le détail de %s : %s", station_id, exc)

    return render_template(
        "station.html",
        station=station,
        station_detail=station_detail_data,
        avg_availability_pct=avg_availability_pct,
    )


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
        "interval": get_effective_settings()["monitor_interval_minutes"],
        "last_run": get_last_collect_run(),
    })


@app.route("/feedbacks")
def feedbacks_page():
    query = (request.args.get("q") or "").strip()
    types = request.args.getlist("type") or None
    sentiments = request.args.getlist("sentiment") or None
    limit = min(int(request.args.get("limit", "50")), 200)
    feedbacks = search_feedbacks(query, types=types, sentiments=sentiments, limit=limit)
    counts = get_feedback_counts()
    return render_template(
        "feedbacks.html",
        feedbacks=feedbacks,
        query=query,
        selected_types=types or [],
        selected_sentiments=sentiments or [],
        counts=counts,
        limit=limit,
    )


@app.route("/api/feedbacks/search")
def api_feedbacks_search():
    query = (request.args.get("q") or "").strip()
    types = request.args.getlist("type") or None
    sentiments = request.args.getlist("sentiment") or None
    limit = min(int(request.args.get("limit", "50")), 200)
    return jsonify({
        "feedbacks": search_feedbacks(query, types=types, sentiments=sentiments, limit=limit),
        "counts": get_feedback_counts(),
    })


@app.route("/api/feedbacks/stats")
def api_feedbacks_stats():
    return jsonify(get_feedback_counts())


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


@app.route("/api/stats/<station_id>")
def api_station_stats(station_id):
    hours = int(request.args.get("hours", "720"))
    return jsonify(get_station_stats(station_id, hours=hours))


@app.route("/api/stations/stats")
def api_stations_stats():
    hours = int(request.args.get("hours", "720"))
    return jsonify(get_all_stations_stats(hours=hours))


@app.route("/api/heatmap/<station_id>")
def api_heatmap(station_id):
    days = int(request.args.get("days", "30"))
    return jsonify(get_hourly_heatmap(station_id, days=days))


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
    interval = get_effective_settings()["monitor_interval_minutes"]
    return render_template("aide.html", interval=interval)


@app.route("/carte")
def carte_page():
    settings = get_effective_settings()
    return render_template(
        "carte.html",
        trajets=[t["name"] for t in get_trajets()],
        default_connector_type=settings["default_connector_type"],
    )


@app.route("/parametres")
def parametres_page():
    return render_template(
        "parametres.html",
        trajets=get_trajets(),
        settings=get_effective_settings(),
        connectors=CONNECTOR_LABELS,
    )


@app.route("/api/settings", methods=["POST"])
def api_settings_save():
    data = request.get_json(silent=True) or {}
    values = {}
    if "app_name" in data:
        values["app_name"] = (data["app_name"] or "").strip() or None
    if "app_subtitle" in data:
        values["app_subtitle"] = (data["app_subtitle"] or "").strip() or None
    if "default_connector_type" in data:
        connector = data["default_connector_type"]
        if connector not in CONNECTOR_LABELS:
            return jsonify({"error": f"Connecteur inconnu : {connector}"}), 400
        values["default_connector_type"] = connector
    if "monitor_interval_minutes" in data:
        try:
            interval = int(data["monitor_interval_minutes"])
        except (ValueError, TypeError):
            return jsonify({"error": "L'intervalle de collecte doit être un entier"}), 400
        if interval < 1:
            return jsonify({
                "error": "L'intervalle de collecte doit être d'au moins 1 minute"
            }), 400
        values["monitor_interval_minutes"] = interval
    if "show_station_details" in data:
        values["show_station_details"] = bool(data["show_station_details"])
    save_settings(values)
    logger.info("Préférences mises à jour : %s", sorted(values))
    return jsonify({"ok": True, "settings": get_effective_settings()})


@app.route("/api/settings/reset", methods=["POST"])
def api_settings_reset():
    reset_settings()
    logger.info("Préférences réinitialisées")
    return jsonify({"ok": True, "settings": get_effective_settings()})


@app.route("/api/trajets/rename", methods=["POST"])
def api_trajets_rename():
    data = request.get_json(silent=True) or {}
    old = (data.get("old") or "").strip()
    new = (data.get("new") or "").strip()
    if not old or not new:
        return jsonify({"error": "Les noms ancien et nouveau sont requis"}), 400
    try:
        updated = rename_trajet(old, new)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    logger.info("Trajet renommé : %s → %s (%d stations)", old, new, updated)
    return jsonify({"ok": True, "updated": updated})


@app.route("/api/trajets/delete", methods=["POST"])
def api_trajets_delete():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Nom de trajet requis"}), 400
    try:
        updated = delete_trajet(name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    logger.info("Trajet supprimé : %s (%d stations détachées)", name, updated)
    return jsonify({"ok": True, "updated": updated})


@app.route("/api/stations/nearby")
def api_stations_nearby():
    try:
        lat = float(request.args.get("lat", ""))
        lon = float(request.args.get("lon", ""))
    except ValueError:
        return jsonify({"error": "Paramètres lat/lon invalides"}), 400
    try:
        radius = float(request.args.get("radius", "10"))
    except ValueError:
        return jsonify({"error": "Paramètre radius invalide"}), 400
    if not 0 < radius <= 100:
        return jsonify({"error": "Le rayon doit être compris entre 0 et 100 km"}), 400
    try:
        results = search_nearby(lat, lon, radius_km=radius)
        return jsonify({"results": results})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:
        logger.exception("Erreur lors de la recherche à proximité (%.4f, %.4f)", lat, lon)
        return jsonify({"error": str(exc)}), 500


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
    connector_type = (
        data.get("connector_type") or get_effective_settings()["default_connector_type"]
    )
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


@app.route("/api/stations/<station_id>/edit", methods=["POST"])
def api_stations_edit(station_id):
    data = request.get_json(silent=True) or {}
    fields = {}
    for key in ("name", "operator", "address", "direction", "connector_type"):
        if key in data:
            fields[key] = data[key]
    if "display_order" in data:
        try:
            fields["display_order"] = int(data["display_order"])
        except (ValueError, TypeError):
            return jsonify({"error": "L'ordre d'affichage doit être un entier"}), 400

    if "connector_type" in fields:
        # On revalide le total de bornes pour le nouveau connecteur.
        try:
            slug = extract_slug(station_id)
            info = get_station_info(slug, fields["connector_type"])
            if info["chademo_total"] == 0:
                return jsonify({
                    "error": f"Aucun connecteur {connector_label(fields['connector_type'])} "
                             f"trouvé pour la station {info.get('name') or slug}"
                }), 400
            fields["chademo_total"] = info["chademo_total"]
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            logger.exception("Erreur lors de la validation du connecteur pour %s", station_id)
            return jsonify({"error": str(exc)}), 500

    try:
        update_station(station_id, fields)
        return jsonify({"ok": True})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Erreur lors de la modification de la station %s", station_id)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stations/<station_id>/refresh", methods=["POST"])
def api_stations_refresh(station_id):
    """Rafraîchit les métadonnées Chargemap d'une station existante (pool_id, logo, etc.)."""
    stations = {s["id"]: s for s in get_all_stations()}
    if station_id not in stations:
        return jsonify({"error": "Station non trouvée"}), 404
    try:
        station = refresh_station_metadata(station_id)
        logger.info("Métadonnées rafraîchies pour %s", station_id)
        return jsonify({"ok": True, "station": station})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Erreur lors du rafraîchissement de %s", station_id)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/export/history/<station_id>")
def api_export_history(station_id):
    """Exporte l'historique d'une station au format CSV."""
    stations = {s["id"]: s for s in get_all_stations()}
    if station_id not in stations:
        return jsonify({"error": "Station non trouvée"}), 404

    hours = int(request.args.get("hours", "720"))
    history = get_history(station_id, hours=hours)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "timestamp", "station_id", "available", "occupied", "busy",
        "unavailable", "reserved", "unknown", "out_of_service",
        "out_of_order", "total",
    ])
    for row in history:
        writer.writerow([
            row["timestamp"],
            row["station_id"],
            row["available"],
            row["occupied"],
            row["busy"],
            row["unavailable"],
            row["reserved"],
            row["unknown"],
            row["out_of_service"],
            row["out_of_order"],
            row["total"],
        ])

    station_name = stations[station_id].get("name") or station_id
    filename = f"historique_{station_id}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/api/export/logs")
def api_export_logs():
    """Exporte les logs d'erreur au format CSV."""
    hours = int(request.args.get("hours", "24"))
    level = request.args.get("level") or None
    errors = get_recent_errors(hours=hours, level=level)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "timestamp", "station_id", "source", "level", "message", "details",
    ])
    for row in errors:
        writer.writerow([
            row["timestamp"],
            row["station_id"],
            row["source"],
            row["level"],
            row["message"],
            row["details"],
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=logs.csv"},
    )

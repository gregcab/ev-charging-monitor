import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ev_monitor.config import (
    APP_NAME,
    APP_SUBTITLE,
    DB_PATH,
    DEFAULT_CONNECTOR_TYPE,
    MONITOR_INTERVAL_MINUTES,
    STATIONS_FILE,
)


def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                operator TEXT,
                address TEXT,
                lat REAL,
                lon REAL,
                charging_availability_id TEXT NOT NULL,
                chademo_total INTEGER,
                direction TEXT,
                created_at TEXT NOT NULL
            )
        """)
        try:
            conn.execute("ALTER TABLE stations ADD COLUMN direction TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute(
                "ALTER TABLE stations ADD COLUMN connector_type TEXT NOT NULL DEFAULT 'CHADEMO'"
            )
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute(
                "ALTER TABLE stations ADD COLUMN display_order INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS availability_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                available INTEGER,
                occupied INTEGER,
                reserved INTEGER,
                unknown INTEGER,
                out_of_service INTEGER,
                total INTEGER,
                FOREIGN KEY (station_id) REFERENCES stations(id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_log_station_time
            ON availability_log(station_id, timestamp)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS collect_run (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                status TEXT NOT NULL,
                error_count INTEGER NOT NULL,
                station_count INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_collect_run_timestamp
            ON collect_run(timestamp DESC)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS error_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                station_id TEXT,
                source TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                details TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_error_log_timestamp
            ON error_log(timestamp DESC)
        """)
        conn.commit()
    finally:
        conn.close()


def load_stations_from_json():
    with open(STATIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_stations_to_json(stations):
    with open(STATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(stations, f, indent=2, ensure_ascii=False)


def add_station(station):
    """Ajoute une station à la liste validée et à la base."""
    stations = load_stations_from_json()
    if any(s["id"] == station["id"] for s in stations):
        raise ValueError(f"La station {station['id']} existe déjà")
    stations.append(station)
    save_stations_to_json(stations)
    seed_stations()


_EDITABLE_FIELDS = {"name", "operator", "address", "direction", "connector_type", "chademo_total", "display_order"}


def update_station(station_id, fields):
    """Met à jour les champs modifiables d'une station dans le JSON et en base."""
    stations = load_stations_from_json()
    station = next((s for s in stations if s["id"] == station_id), None)
    if not station:
        raise ValueError(f"Station inconnue : {station_id}")

    for key, value in fields.items():
        if key in _EDITABLE_FIELDS:
            station[key] = value

    save_stations_to_json(stations)
    seed_stations()


def seed_stations():
    stations = load_stations_from_json()
    conn = sqlite3.connect(DB_PATH)
    try:
        for station in stations:
            conn.execute(
                """
                INSERT OR IGNORE INTO stations (id, name, operator, address, direction, lat, lon,
                                                charging_availability_id, chademo_total,
                                                connector_type, display_order, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    station["id"],
                    station["name"],
                    station.get("operator"),
                    station.get("address"),
                    station.get("direction"),
                    station.get("lat"),
                    station.get("lon"),
                    station["charging_availability_id"],
                    station.get("chademo_total"),
                    station.get("connector_type", "CHADEMO"),
                    station.get("display_order", 0),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.execute(
                """
                UPDATE stations
                SET name = ?, operator = ?, address = ?, direction = ?, lat = ?, lon = ?,
                    charging_availability_id = ?, chademo_total = ?, connector_type = ?,
                    display_order = ?
                WHERE id = ?
                """,
                (
                    station["name"],
                    station.get("operator"),
                    station.get("address"),
                    station.get("direction"),
                    station.get("lat"),
                    station.get("lon"),
                    station["charging_availability_id"],
                    station.get("chademo_total"),
                    station.get("connector_type", "CHADEMO"),
                    station.get("display_order", 0),
                    station["id"],
                ),
            )
        conn.commit()
    finally:
        conn.close()


def save_availability(station_id, availability, total):
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            INSERT INTO availability_log (station_id, timestamp, available, occupied, reserved,
                                          unknown, out_of_service, total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                station_id,
                now,
                availability.get("available", 0),
                availability.get("occupied", 0),
                availability.get("reserved", 0),
                availability.get("unknown", 0),
                availability.get("outOfService", 0),
                total,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_all_stations():
    validated_ids = {s["id"] for s in load_stations_from_json()}
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM stations ORDER BY lon").fetchall()
        return [dict(row) for row in rows if dict(row)["id"] in validated_ids]
    finally:
        conn.close()


def get_latest_availability(station_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT * FROM availability_log
            WHERE station_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (station_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_history(station_id, hours=24):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT * FROM availability_log
            WHERE station_id = ? AND datetime(timestamp) > datetime('now', ?)
            ORDER BY timestamp ASC
            """,
            (station_id, f"-{hours} hours"),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_last_zero_availability(station_id):
    """Retourne le timestamp de la dernière mesure où available == 0."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT timestamp FROM availability_log
            WHERE station_id = ? AND available = 0
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (station_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def save_collect_run(status, error_count, station_count):
    """Enregistre le résultat d'un cycle de collecte."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            INSERT INTO collect_run (timestamp, status, error_count, station_count)
            VALUES (?, ?, ?, ?)
            """,
            (now, status, error_count, station_count),
        )
        conn.commit()
    finally:
        conn.close()


def get_last_collect_run():
    """Retourne le dernier cycle de collecte."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT * FROM collect_run
            ORDER BY timestamp DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _cleanup_old_errors(conn, days=7):
    """Supprime les logs d'erreur de plus de `days` jours."""
    conn.execute(
        "DELETE FROM error_log WHERE datetime(timestamp) < datetime('now', ?)",
        (f"-{days} days",),
    )


def log_error(source, level, message, station_id=None, details=None):
    """Enregistre une erreur ou un avertissement."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            INSERT INTO error_log (timestamp, station_id, source, level, message, details)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (now, station_id, source, level, message, details),
        )
        _cleanup_old_errors(conn)
        conn.commit()
    finally:
        conn.close()


def get_recent_errors(hours=24, level=None):
    """Retourne les erreurs des dernières `hours` heures, optionnellement filtrées par niveau."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        sql = """
            SELECT * FROM error_log
            WHERE datetime(timestamp) > datetime('now', ?)
        """
        params = [f"-{hours} hours"]
        if level:
            sql += " AND level = ?"
            params.append(level)
        sql += " ORDER BY timestamp DESC"
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_error_stats(hours=24):
    """Retourne les statistiques d'erreurs sur les dernières `hours` heures."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT level, COUNT(*) as count
            FROM error_log
            WHERE datetime(timestamp) > datetime('now', ?)
            GROUP BY level
            """,
            (f"-{hours} hours",),
        ).fetchall()
        stats = {"total": 0, "error": 0, "warning": 0}
        for row in rows:
            stats[row["level"]] = row["count"]
            stats["total"] += row["count"]
        return stats
    finally:
        conn.close()


def clear_errors(hours=None):
    """Efface les logs d'erreur.

    Si `hours` est fourni, seuls les logs des dernières `hours` heures sont supprimés.
    Sinon, toute la table est vidée.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        if hours is not None:
            conn.execute(
                "DELETE FROM error_log WHERE datetime(timestamp) > datetime('now', ?)",
                (f"-{hours} hours",),
            )
        else:
            conn.execute("DELETE FROM error_log")
        conn.commit()
    finally:
        conn.close()


def get_station_stats(station_id, hours=720):
    """Retourne les statistiques de fiabilité d'une station sur les dernières `hours` heures."""
    history = get_history(station_id, hours=hours)
    total = len(history)
    if total == 0:
        return {
            "station_id": station_id,
            "period_hours": hours,
            "total_measurements": 0,
            "avg_availability_pct": None,
            "zero_availability_count": 0,
            "zero_availability_pct": 0.0,
            "occupied_count": 0,
            "out_of_service_count": 0,
            "unknown_count": 0,
            "best_hour": None,
            "worst_hour": None,
            "estimated_downtime_hours": 0.0,
        }

    zero_count = 0
    occupied_count = 0
    out_of_service_count = 0
    unknown_count = 0
    availability_values = []
    hourly_values = {h: [] for h in range(24)}

    for row in history:
        from datetime import datetime

        dt = datetime.fromisoformat(row["timestamp"])
        hour = dt.hour
        avail = row.get("available", 0)
        occ = row.get("occupied", 0)
        oos = row.get("out_of_service", 0)
        unk = row.get("unknown", 0)
        total_slots = row.get("total") or 1
        ratio = avail / total_slots
        availability_values.append(ratio)
        hourly_values[hour].append(ratio)

        if avail == 0:
            zero_count += 1
            if occ > 0:
                occupied_count += 1
            elif oos > 0:
                out_of_service_count += 1
            elif unk > 0:
                unknown_count += 1

    hourly_avgs = {
        h: (sum(vals) / len(vals) if vals else None)
        for h, vals in hourly_values.items()
    }
    ranked = [(h, avg) for h, avg in hourly_avgs.items() if avg is not None]
    best_hour = min(ranked, key=lambda x: -x[1])[0] if ranked else None
    worst_hour = min(ranked, key=lambda x: x[1])[0] if ranked else None

    estimated_downtime_hours = (zero_count * MONITOR_INTERVAL_MINUTES) / 60.0

    return {
        "station_id": station_id,
        "period_hours": hours,
        "total_measurements": total,
        "avg_availability_pct": round(sum(availability_values) / total * 100, 1),
        "zero_availability_count": zero_count,
        "zero_availability_pct": round(zero_count / total * 100, 1),
        "occupied_count": occupied_count,
        "out_of_service_count": out_of_service_count,
        "unknown_count": unknown_count,
        "best_hour": best_hour,
        "worst_hour": worst_hour,
        "estimated_downtime_hours": round(estimated_downtime_hours, 1),
    }


def get_all_stations_stats(hours=720):
    """Retourne les statistiques de fiabilité pour toutes les stations validées."""
    stations = get_all_stations()
    return [get_station_stats(s["id"], hours=hours) for s in stations]


def get_hourly_heatmap(station_id, days=30):
    """Calcule le taux moyen de disponibilité par jour de semaine (0=lundi) et heure.

    Retourne une matrice 7×24 : liste de 7 jours, chacun contenant 24 pourcentages.
    """
    history = get_history(station_id, hours=days * 24)
    if not history:
        return {"days": ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"], "matrix": [[None] * 24 for _ in range(7)]}

    buckets = {(d, h): [] for d in range(7) for h in range(24)}
    for row in history:
        from datetime import datetime

        dt = datetime.fromisoformat(row["timestamp"])
        # weekday() renvoie 0=lundi, 6=dimanche
        day = dt.weekday()
        hour = dt.hour
        total = row.get("total") or 1
        buckets[(day, hour)].append(row.get("available", 0) / total)

    matrix = []
    for day in range(7):
        day_values = []
        for hour in range(24):
            vals = buckets[(day, hour)]
            day_values.append(round(sum(vals) / len(vals) * 100, 1) if vals else None)
        matrix.append(day_values)

    return {
        "days": ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
        "hours": list(range(24)),
        "matrix": matrix,
    }


def get_settings():
    """Retourne les préférences stockées en base (table settings)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: row["value"] for row in rows}
    finally:
        conn.close()


def save_settings(values):
    """Enregistre les préférences données dans la table settings.

    Une valeur `None` supprime la clé (retour à la valeur d'env/défaut).
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        for key, value in values.items():
            if value is None:
                conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            else:
                conn.execute(
                    """
                    INSERT INTO settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, str(value)),
                )
        conn.commit()
    finally:
        conn.close()


def reset_settings():
    """Supprime toutes les préférences stockées (retour aux valeurs d'env/défaut)."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("DELETE FROM settings")
        conn.commit()
    finally:
        conn.close()


def get_effective_settings():
    """Fusionne les préférences : valeur en base > variable d'env > défaut embarqué."""
    stored = get_settings()
    return {
        "app_name": stored.get("app_name") or APP_NAME,
        "app_subtitle": stored.get("app_subtitle") or APP_SUBTITLE,
        "default_connector_type": (
            stored.get("default_connector_type") or DEFAULT_CONNECTOR_TYPE
        ),
        "monitor_interval_minutes": int(
            stored.get("monitor_interval_minutes") or MONITOR_INTERVAL_MINUTES
        ),
    }


def get_trajets():
    """Retourne les trajets existants (directions distinctes) et leur nombre de stations."""
    counts = {}
    for station in get_all_stations():
        direction = station.get("direction")
        if direction:
            counts[direction] = counts.get(direction, 0) + 1
    return [
        {"name": name, "station_count": count}
        for name, count in sorted(counts.items())
    ]


def rename_trajet(old_name, new_name):
    """Renomme un trajet dans le JSON des stations puis resynchronise la base.

    Si `new_name` existe déjà, les stations fusionnent dans le trajet existant.
    Retourne le nombre de stations mises à jour.
    """
    stations = load_stations_from_json()
    updated = 0
    for station in stations:
        if station.get("direction") == old_name:
            station["direction"] = new_name
            updated += 1
    if updated == 0:
        raise ValueError(f"Trajet inconnu : {old_name}")
    save_stations_to_json(stations)
    seed_stations()
    return updated


def delete_trajet(name):
    """Détache les stations d'un trajet (direction = null) sans les supprimer.

    Retourne le nombre de stations mises à jour.
    """
    stations = load_stations_from_json()
    updated = 0
    for station in stations:
        if station.get("direction") == name:
            station["direction"] = None
            updated += 1
    if updated == 0:
        raise ValueError(f"Trajet inconnu : {name}")
    save_stations_to_json(stations)
    seed_stations()
    return updated

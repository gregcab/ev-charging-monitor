import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ev_monitor.config import DB_PATH, STATIONS_FILE


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


def seed_stations():
    stations = load_stations_from_json()
    conn = sqlite3.connect(DB_PATH)
    try:
        for station in stations:
            conn.execute(
                """
                INSERT OR IGNORE INTO stations (id, name, operator, address, direction, lat, lon,
                                                charging_availability_id, chademo_total,
                                                connector_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.execute(
                """
                UPDATE stations
                SET name = ?, operator = ?, address = ?, direction = ?, lat = ?, lon = ?,
                    charging_availability_id = ?, chademo_total = ?, connector_type = ?
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
            WHERE station_id = ? AND timestamp > datetime('now', ?)
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
        "DELETE FROM error_log WHERE timestamp < datetime('now', ?)",
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
            WHERE timestamp > datetime('now', ?)
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
            WHERE timestamp > datetime('now', ?)
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
                "DELETE FROM error_log WHERE timestamp > datetime('now', ?)",
                (f"-{hours} hours",),
            )
        else:
            conn.execute("DELETE FROM error_log")
        conn.commit()
    finally:
        conn.close()

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
        conn.commit()
    finally:
        conn.close()


def load_stations_from_json():
    with open(STATIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def seed_stations():
    stations = load_stations_from_json()
    conn = sqlite3.connect(DB_PATH)
    try:
        for station in stations:
            conn.execute(
                """
                INSERT OR IGNORE INTO stations (id, name, operator, address, direction, lat, lon,
                                                charging_availability_id, chademo_total, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.execute(
                """
                UPDATE stations
                SET name = ?, operator = ?, address = ?, direction = ?, lat = ?, lon = ?,
                    charging_availability_id = ?, chademo_total = ?
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

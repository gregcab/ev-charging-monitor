import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.getenv("DB_PATH", os.path.join(BASE_DIR, "ev_monitoring.db"))
# Par défaut, la liste des stations est stockée dans le même répertoire que la base
# SQLite pour être persistée par le même volume en production Docker.
STATIONS_FILE = os.getenv(
    "STATIONS_FILE", os.path.join(os.path.dirname(DB_PATH), "stations_validated.json")
)

MONITOR_INTERVAL_MINUTES = int(os.getenv("MONITOR_INTERVAL_MINUTES", "5"))
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5000"))

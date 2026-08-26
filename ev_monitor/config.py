import os

from dotenv import load_dotenv

load_dotenv()

TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY")
if not TOMTOM_API_KEY:
    raise RuntimeError("Définissez TOMTOM_API_KEY dans .env")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STATIONS_FILE = os.path.join(BASE_DIR, "stations_validated.json")
DB_PATH = os.getenv("DB_PATH", os.path.join(BASE_DIR, "ev_monitoring.db"))

MONITOR_INTERVAL_MINUTES = int(os.getenv("MONITOR_INTERVAL_MINUTES", "5"))
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5000"))

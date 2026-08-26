import requests

from ev_monitor.config import TOMTOM_API_KEY

BASE_URL = "https://api.tomtom.com/search/2"


def get_charging_availability(charging_availability_id):
    url = f"{BASE_URL}/chargingAvailability.json"
    params = {
        "key": TOMTOM_API_KEY,
        "chargingAvailability": charging_availability_id,
        "connectorSet": "Chademo",
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    for connector in data.get("connectors", []):
        if connector.get("type") == "Chademo":
            return connector

    return None

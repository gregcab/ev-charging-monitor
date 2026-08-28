import requests

from ev_monitor.config import TOMTOM_API_KEY

BASE_URL = "https://api.tomtom.com/search/2"


def _truncate(text, max_len=500):
    if text is None:
        return None
    text = str(text)
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def get_charging_availability(charging_availability_id):
    url = f"{BASE_URL}/chargingAvailability.json"
    params = {
        "key": TOMTOM_API_KEY,
        "chargingAvailability": charging_availability_id,
        "connectorSet": "Chademo",
    }
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        response_text = _truncate(exc.response.text) if exc.response is not None else None
        details_parts = [f"status={status_code}"]
        if response_text:
            details_parts.append(f"response={response_text}")
        details_parts.append(f"error={exc}")
        details = ", ".join(details_parts)
        raise RuntimeError(
            f"TomTom {type(exc).__name__} (HTTP {status_code}) pour {charging_availability_id}: {details}"
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Réponse TomTom invalide pour {charging_availability_id}: {exc}"
        ) from exc

    for connector in data.get("connectors", []):
        if connector.get("type") == "Chademo":
            return connector

    return None

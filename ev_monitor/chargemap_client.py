import requests

BASE_URL = "https://map.chargemap.com/pool-detail/v2/pools"

CHARGEMAP_STATE_MAP = {
    "AVAILABLE": "available",
    "BUSY": "occupied",
    "UNAVAILABLE": "occupied",
    "OUT_OF_SERVICE": "outOfService",
    "OUT_OF_ORDER": "outOfService",
    "UNKNOWN": "unknown",
}


def get_charging_availability(slug):
    url = f"{BASE_URL}/{slug}"
    params = {"locale": "fr-fr"}
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Chargemap indisponible pour {slug}: {exc}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Réponse Chargemap invalide pour {slug}: {exc}") from exc

    stations = data.get("stations", [])
    if not stations:
        return None

    counts = {
        "available": 0,
        "occupied": 0,
        "reserved": 0,
        "unknown": 0,
        "outOfService": 0,
    }

    for station in stations:
        if station.get("administrative_state") != "in-service":
            continue
        for connector in station.get("connectors", []):
            if connector.get("type") != "CHADEMO":
                continue
            state = connector.get("realtime_state") or connector.get("overall_state")
            mapped = CHARGEMAP_STATE_MAP.get(state, "unknown")
            counts[mapped] += 1

    total = sum(counts.values())
    return {"availability": {"current": counts}, "total": total}


def get_station_info(slug):
    url = f"{BASE_URL}/{slug}"
    params = {"locale": "fr-fr"}
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Chargemap indisponible pour {slug}: {exc}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Réponse Chargemap invalide pour {slug}: {exc}") from exc

    chademo_count = 0
    for station in data.get("stations", []):
        if station.get("administrative_state") != "in-service":
            continue
        for connector in station.get("connectors", []):
            if connector.get("type") == "CHADEMO":
                chademo_count += 1

    return {
        "id": slug,
        "name": data.get("name"),
        "operator": data.get("network", {}).get("name"),
        "address": f"{data.get('street_name', '')}, {data.get('postal_code', '')} {data.get('city', '')}".strip(", "),
        "lat": float(data.get("coordinates", {}).get("lat", 0)),
        "lon": float(data.get("coordinates", {}).get("lon", 0)),
        "charging_availability_id": slug,
        "chademo_total": chademo_count,
    }

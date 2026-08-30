import math
import re

import requests

from ev_monitor.config import DEFAULT_CONNECTOR_TYPE

BASE_URL = "https://map.chargemap.com/pool-detail/v2/pools"
MAPPY_URL = "https://map.chargemap.com/mappy/charging_pools.json"

CONNECTOR_LABELS = {
    "CHADEMO": "Chademo",
    "COMBO_TYPE_2": "Combo CCS",
    "MENNEKES_TYPE_2": "Type 2",
    "MENNEKES_TYPE_2_CABLE_ATTACHED": "Type 2 (câble attaché)",
    "DOMESTIC_TYPE_F": "Prise domestique",
    "TESLA_SUPERCHARGER_EU": "Tesla Supercharger",
    "TESLA": "Tesla",
}


def connector_label(connector_type):
    """Retourne le libellé français d'un type de connecteur Chargemap."""
    return CONNECTOR_LABELS.get(connector_type, connector_type)

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_POOL_URL_RE = re.compile(r"/pools/([a-z0-9-]+)")
_PAGE_URL_RE = re.compile(r"chargemap\.com/[a-z]{2}-[a-z]{2}/([a-z0-9-]+)")


def extract_slug(text):
    """Extrait le slug Chargemap depuis une URL de page station ou un slug brut."""
    text = (text or "").strip()
    if not text:
        raise ValueError("URL ou slug requis")
    match = _POOL_URL_RE.search(text) or _PAGE_URL_RE.search(text)
    if match:
        return match.group(1)
    if _SLUG_RE.match(text):
        return text
    raise ValueError(f"Impossible de trouver le slug Chargemap dans : {text}")

CHARGEMAP_STATE_MAP = {
    "AVAILABLE": "available",
    "BUSY": "occupied",
    "UNAVAILABLE": "occupied",
    "OUT_OF_SERVICE": "outOfService",
    "OUT_OF_ORDER": "outOfService",
    "UNKNOWN": "unknown",
}


def get_charging_availability(slug, connector_type=DEFAULT_CONNECTOR_TYPE):
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
            if connector.get("type") != connector_type:
                continue
            state = connector.get("realtime_state") or connector.get("overall_state")
            mapped = CHARGEMAP_STATE_MAP.get(state, "unknown")
            counts[mapped] += 1

    total = sum(counts.values())
    return {"availability": {"current": counts}, "total": total}


def get_station_info(slug, connector_type=DEFAULT_CONNECTOR_TYPE):
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

    connector_counts = {}
    for station in data.get("stations", []):
        if station.get("administrative_state") != "in-service":
            continue
        for connector in station.get("connectors", []):
            ctype = connector.get("type")
            if ctype:
                connector_counts[ctype] = connector_counts.get(ctype, 0) + 1

    connectors = [
        {"type": ctype, "count": count}
        for ctype, count in sorted(connector_counts.items())
    ]

    return {
        "id": slug,
        "name": data.get("name"),
        "operator": data.get("network", {}).get("name"),
        "address": f"{data.get('street_name', '')}, {data.get('postal_code', '')} {data.get('city', '')}".strip(", "),
        "lat": float(data.get("coordinates", {}).get("lat", 0)),
        "lon": float(data.get("coordinates", {}).get("lon", 0)),
        "charging_availability_id": slug,
        "connector_type": connector_type,
        # La clé historique `chademo_total` stocke le total du connecteur choisi.
        "chademo_total": connector_counts.get(connector_type, 0),
        "connectors": connectors,
    }


def _pool_to_result(pool, connectors=None):
    """Normalise un pool Chargemap en résultat de recherche."""
    coordinates = pool.get("coordinates") or pool.get("gps_coordinates") or {}
    return {
        "slug": pool.get("slug"),
        "name": pool.get("name"),
        "operator": (pool.get("network") or {}).get("name"),
        "address": f"{pool.get('street_name', '')}, {pool.get('postal_code', '')} {pool.get('city', '')}".strip(", "),
        "lat": float(coordinates.get("lat") or 0),
        "lon": float(coordinates.get("lon") or coordinates.get("lng") or 0),
        "connectors": connectors or [],
    }


def _mappy_connectors(pool):
    """Extrait la liste {type, count} des connecteurs d'un pool mappy."""
    connectors = {}
    for entry in pool.get("charging_connectors") or []:
        ctype = entry.get("type")
        if ctype:
            connectors[ctype] = connectors.get(ctype, 0) + (entry.get("count") or 0)
    return [{"type": ctype, "count": count} for ctype, count in sorted(connectors.items())]


def _search_by_city(query):
    """Recherche les pools d'une ville via l'endpoint mappy (couvre les opérateurs)."""
    params = {"city": query, "state": 2, "limit": 100}
    response = requests.get(MAPPY_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    items = data.get("response", {}).get("content", {}).get("items", [])
    results = []
    for item in items:
        pool = item.get("pool")
        if not pool or not pool.get("slug"):
            continue  # ignore les clusters
        results.append(_pool_to_result(pool, connectors=_mappy_connectors(pool)))
    return results


def _pool_detail_connectors(pool):
    """Extrait la liste {type, count} des connecteurs d'un pool pool-detail."""
    connectors = {}
    for station in pool.get("stations") or []:
        for connector in station.get("connectors") or []:
            ctype = connector.get("type")
            if ctype:
                connectors[ctype] = connectors.get(ctype, 0) + 1
    return [{"type": ctype, "count": count} for ctype, count in sorted(connectors.items())]


def _search_by_name(query):
    """Recherche par nom via l'endpoint pool-detail (pools communautaires)."""
    params = {"name": query, "locale": "fr-fr"}
    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    results = []
    for pool in data.get("items", []):
        if pool.get("state") == "DELETED" or not pool.get("slug"):
            continue
        results.append(_pool_to_result(pool, connectors=_pool_detail_connectors(pool)))
    return results


def search_stations(query):
    """Recherche des stations Chargemap par nom ou ville.

    Combine la recherche par ville (mappy) et par nom (pool-detail), fusionnées
    par slug. Aucun filtre sur le type de connecteur : l'utilisateur choisit.
    """
    query = (query or "").strip()
    if not query:
        raise ValueError("Terme de recherche requis")

    try:
        by_city = _search_by_city(query)
        by_name = _search_by_name(query)
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Recherche Chargemap indisponible : {exc}") from exc
    except ValueError as exc:
        raise RuntimeError(f"Réponse Chargemap invalide : {exc}") from exc

    merged = {r["slug"]: r for r in by_name}
    merged.update({r["slug"]: r for r in by_city})  # mappy est plus riche, il gagne
    return sorted(merged.values(), key=lambda r: (r.get("name") or "").lower())


def _haversine_km(lat1, lon1, lat2, lon2):
    """Distance en kilomètres entre deux points (formule de haversine)."""
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def search_nearby(lat, lon, radius_km=10):
    """Recherche les stations Chargemap dans un rayon autour d'un point.

    Utilise la recherche bbox de l'endpoint mappy (coins `NW` et `SE` au format
    « lat;lng »), puis filtre et trie les résultats par distance réelle.
    """
    lat = float(lat)
    lon = float(lon)
    radius_km = float(radius_km)
    # Conversion approximative du rayon en degrés pour la bbox.
    delta_lat = radius_km / 111.0
    delta_lon = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.01))
    params = {
        "NW": f"{lat + delta_lat};{lon - delta_lon}",
        "SE": f"{lat - delta_lat};{lon + delta_lon}",
        "state": 2,
        "limit": 100,
    }
    try:
        response = requests.get(MAPPY_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Recherche Chargemap indisponible : {exc}") from exc
    except ValueError as exc:
        raise RuntimeError(f"Réponse Chargemap invalide : {exc}") from exc

    items = data.get("response", {}).get("content", {}).get("items", [])
    results = []
    for item in items:
        pool = item.get("pool")
        if not pool or not pool.get("slug"):
            continue  # ignore les clusters
        result = _pool_to_result(pool, connectors=_mappy_connectors(pool))
        result["distance_km"] = round(
            _haversine_km(lat, lon, result["lat"], result["lon"]), 1
        )
        if result["distance_km"] <= radius_km:
            results.append(result)
    return sorted(results, key=lambda r: r["distance_km"])

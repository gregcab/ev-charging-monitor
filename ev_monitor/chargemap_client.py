import math
import re

import requests

from ev_monitor.config import DEFAULT_CONNECTOR_TYPE

BASE_URL = "https://map.chargemap.com/pool-detail/v2/pools"
MAPPY_URL = "https://map.chargemap.com/mappy/charging_pools.json"
FEEDBACKS_URL = "https://map.chargemap.com/community-feedbacks/feedbacks"

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
    "BUSY": "busy",
    "UNAVAILABLE": "unavailable",
    "OUT_OF_SERVICE": "outOfService",
    "OUT_OF_ORDER": "outOfOrder",
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
        "busy": 0,
        "unavailable": 0,
        "reserved": 0,
        "unknown": 0,
        "outOfOrder": 0,
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

    # Agrégats conservés pour la rétrocompatibilité des templates/graphiques.
    counts["occupied"] = counts["busy"] + counts["unavailable"]
    counts["outOfService"] = counts["outOfOrder"]

    total = (
        counts["available"]
        + counts["busy"]
        + counts["unavailable"]
        + counts["reserved"]
        + counts["unknown"]
        + counts["outOfOrder"]
    )
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
    connector_powers = {}
    for station in data.get("stations", []):
        if station.get("administrative_state") != "in-service":
            continue
        for connector in station.get("connectors", []):
            ctype = connector.get("type")
            if not ctype:
                continue
            connector_counts[ctype] = connector_counts.get(ctype, 0) + 1
            power = connector.get("power") or 0
            connector_powers[ctype] = max(connector_powers.get(ctype, 0), power)

    connectors = [
        {"type": ctype, "count": count, "power_max": connector_powers.get(ctype)}
        for ctype, count in sorted(connector_counts.items())
    ]

    network = data.get("network") or {}
    coordinates = data.get("coordinates") or {}
    owner = data.get("owner") or {}

    # Passes compatibles mis en avant
    passes = []
    auth_methods = set()
    for station in data.get("stations", []):
        for method in station.get("authentication_methods") or []:
            auth_methods.add(method)
        for p in station.get("highlighted_passes") or []:
            passes.append({"id": p.get("id"), "name": p.get("name"), "highlighted": True})
        for p in station.get("third_party_passes") or []:
            passes.append({"id": p.get("id"), "name": p.get("name"), "highlighted": False})
    # Dédupliquer les passes par nom
    seen = set()
    unique_passes = []
    for p in passes:
        if p["name"] and p["name"] not in seen:
            seen.add(p["name"])
            unique_passes.append(p)

    return {
        "id": slug,
        "pool_id": data.get("id"),
        "name": data.get("name"),
        "operator": network.get("name"),
        "operator_logo_url": network.get("logo_url"),
        "operator_rating": network.get("average_rating"),
        "operator_rating_count": network.get("rating_count"),
        "owner_name": owner.get("name"),
        "owner_website": owner.get("website"),
        "address": f"{data.get('street_name', '')}, {data.get('postal_code', '')} {data.get('city', '')}".strip(", "),
        "lat": float(coordinates.get("lat", 0)),
        "lon": float(coordinates.get("lon", 0)),
        "charging_availability_id": slug,
        "connector_type": connector_type,
        # La clé historique `chademo_total` stocke le total du connecteur choisi.
        "chademo_total": connector_counts.get(connector_type, 0),
        "max_power": connector_powers.get(connector_type),
        "connectors": connectors,
        "amenities": data.get("amenities") or [],
        "always_open": data.get("always_open") or False,
        "is_free": data.get("is_free") or False,
        "parking_free": data.get("parking_free") or False,
        "indoor": data.get("indoor") or False,
        "is_tesla": data.get("is_tesla") or False,
        "access": data.get("access"),
        "location": data.get("location"),
        "speed": data.get("speed"),
        "rating": data.get("rating"),
        "rating_count": data.get("rating_count"),
        "statistic": data.get("statistic") or {},
        "description": data.get("description"),
        "schedules": data.get("schedules") or [],
        "avatar_url": data.get("avatar_url"),
        "cover_url": data.get("cover_url"),
        "should_check_prices": data.get("should_check_prices") or False,
        "authentication_methods": sorted(auth_methods),
        "passes": unique_passes,
    }


def get_station_detail(slug, connector_type=DEFAULT_CONNECTOR_TYPE):
    """Retourne le détail des bornes physiques et de leurs connecteurs.

    Inclut la puissance, le voltage, l'intensité, le type de courant,
    l'état temps réel et les compatibilités de chaque connecteur.
    """
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

    stations = []
    for station in data.get("stations", []):
        if station.get("administrative_state") != "in-service":
            continue
        connectors = []
        for connector in station.get("connectors", []):
            state = connector.get("realtime_state") or connector.get("overall_state")
            mapped = CHARGEMAP_STATE_MAP.get(state, "unknown")
            connectors.append({
                "id": connector.get("id"),
                "type": connector.get("type"),
                "power": connector.get("power"),
                "voltage": connector.get("voltage"),
                "intensity": connector.get("intensity"),
                "current_type": connector.get("current_type"),
                "state": mapped,
                "raw_state": state,
                "is_bookable": connector.get("is_bookable") or False,
                "evse_id": connector.get("evse_id"),
                "remote_identifier": connector.get("remote_identifier"),
                "is_remote_charge_compatible": connector.get("is_remote_charge_compatible") or False,
                "is_auto_charge_compatible": connector.get("is_auto_charge_compatible") or False,
                "is_plug_and_charge_compatible": connector.get("is_plug_and_charge_compatible") or False,
                "is_monitored": connector.get("type") == connector_type,
            })
        if connectors:
            stations.append({
                "id": station.get("id"),
                "label": station.get("label"),
                "administrative_state": station.get("administrative_state"),
                "connectors": connectors,
            })
    return {"stations": stations}


def _pool_to_result(pool, connectors=None):
    """Normalise un pool Chargemap en résultat de recherche."""
    coordinates = pool.get("coordinates") or pool.get("gps_coordinates") or {}
    network = pool.get("network") or {}
    connectors = connectors or []
    power_max = None
    if connectors:
        powers = [c.get("power_max") for c in connectors if c.get("power_max")]
        if powers:
            power_max = max(powers)

    # Normalisation de la vitesse (string ou objet) et de l'emplacement.
    speed = pool.get("speed")
    if isinstance(speed, dict):
        speed = speed.get("id")
    location = pool.get("location") or pool.get("location_type_slug")

    return {
        "slug": pool.get("slug"),
        "name": pool.get("name"),
        "operator": network.get("name"),
        "operator_logo_url": network.get("logo_url"),
        "address": f"{pool.get('street_name', '')}, {pool.get('postal_code', '')} {pool.get('city', '')}".strip(", "),
        "lat": float(coordinates.get("lat") or 0),
        "lon": float(coordinates.get("lon") or coordinates.get("lng") or 0),
        "connectors": connectors,
        "power_max": power_max,
        "speed": speed,
        "location": location,
        "operational_status": pool.get("operational_status"),
        "availability_status": pool.get("availability_status"),
        "real_time_available": pool.get("real_time_available") or False,
        "always_open": pool.get("is_always_open") or pool.get("always_open") or False,
        "is_free": pool.get("is_free") or False,
        "is_tesla": pool.get("is_tesla") or False,
        "amenities": pool.get("amenities") or [],
        "rating": pool.get("rating"),
        "rating_count": pool.get("rating_count"),
    }


def _mappy_connectors(pool):
    """Extrait la liste {type, count, power_max} des connecteurs d'un pool mappy."""
    connectors = {}
    for entry in pool.get("charging_connectors") or []:
        ctype = entry.get("type")
        if not ctype:
            continue
        if ctype not in connectors:
            connectors[ctype] = {"count": 0, "power_max": 0}
        connectors[ctype]["count"] += entry.get("count") or 0
        connectors[ctype]["power_max"] = max(
            connectors[ctype]["power_max"], entry.get("power_max") or 0
        )
    return [
        {"type": ctype, "count": data["count"], "power_max": data["power_max"] or None}
        for ctype, data in sorted(connectors.items())
    ]


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
    """Extrait la liste {type, count, power_max} des connecteurs d'un pool pool-detail."""
    connectors = {}
    for station in pool.get("stations") or []:
        for connector in station.get("connectors") or []:
            ctype = connector.get("type")
            if not ctype:
                continue
            if ctype not in connectors:
                connectors[ctype] = {"count": 0, "power_max": 0}
            connectors[ctype]["count"] += 1
            connectors[ctype]["power_max"] = max(
                connectors[ctype]["power_max"], connector.get("power") or 0
            )
    return [
        {"type": ctype, "count": data["count"], "power_max": data["power_max"] or None}
        for ctype, data in sorted(connectors.items())
    ]


def _search_by_name(query):
    """Recherche par nom via l'endpoint pool-detail (pools communautaires)."""
    params = {"name": query, "locale": "fr-fr"}
    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    results = []
    for pool in data.get("items", []):
        # Ne proposer que les pools publiés ; CREATING est ignoré.
        if pool.get("state") != "PUBLISHED" or not pool.get("slug"):
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


def _normalize_feedback(item):
    """Normalise un feedback brut Chargemap en dict interne."""
    content = item.get("comment") or ""
    rating = item.get("rating") or {}
    if not content:
        content = rating.get("comment") or ""
    response = (item.get("chargemap_response") or {}).get("public_content") or ""
    return {
        "feedback_id": item["id"],
        "type": item.get("type"),
        "username": item.get("user_username"),
        "created_at": item.get("creation_date"),
        "content": content.strip(),
        "response_content": response.strip(),
        "reason_type": item.get("reason_type"),
        "sentiment": item.get("sentiment") or rating.get("sentiment"),
        "locale": item.get("locale"),
    }


def get_pool_feedbacks(pool_id, limit=100):
    """Récupère les feedbacks d'une station (checkins, commentaires, signalements).

    Paginate l'endpoint community-feedbacks jusqu'à `limit` items.
    """
    if not pool_id:
        return []
    feedbacks = []
    offset = 0
    page_size = min(limit, 100)
    while len(feedbacks) < limit:
        params = {
            "pool_id": pool_id,
            "offset": offset,
            "limit": page_size,
            "feedback_type": "",
            "moderation_status": "VALIDATED,PENDING",
        }
        try:
            response = requests.get(FEEDBACKS_URL, params=params, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Feedbacks Chargemap indisponibles pour {pool_id}: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Réponse feedbacks invalide pour {pool_id}: {exc}") from exc

        items = data.get("items", [])
        if not items:
            break
        for item in items:
            feedbacks.append(_normalize_feedback(item))
            if len(feedbacks) >= limit:
                break
        if len(items) < page_size:
            break
        offset += page_size
    return feedbacks


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

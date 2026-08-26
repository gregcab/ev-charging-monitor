#!/usr/bin/env python3
"""Découvre les stations de recharge candidates sur l'autoroute A8 entre Saint-Maximin et Cannes.

Génère un fichier `stations_candidates.json` à valider manuellement avant de lancer le monitoring.
"""

import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY")
if not TOMTOM_API_KEY:
    raise RuntimeError("Définissez TOMTOM_API_KEY dans .env")

BASE_URL = "https://api.tomtom.com/search/2"

# Points de contrôle le long de l'A8 (d'ouest en est)
CHECKPOINTS = [
    ("Saint-Maximin", 43.4541, 5.86205),
    ("Cambarette", 43.423878, 5.990385),
    ("Vidauban", 43.414, 6.451),
    ("Fréjus", 43.437, 6.737),
    ("Bréguières", 43.595, 6.985),
    ("Cannes", 43.55121, 7.0181),
]

RADIUS_METERS = 10000
OUTPUT_FILE = "stations_candidates.json"


def fetch_all_stations():
    url = f"{BASE_URL}/nearbySearch/.json"
    seen = {}
    for label, lat, lon in CHECKPOINTS:
        params = {
            "key": TOMTOM_API_KEY,
            "lat": lat,
            "lon": lon,
            "radius": RADIUS_METERS,
            "limit": 100,
            "categorySet": "7309",  # Electric Vehicle Station
        }
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        for result in data.get("results", []):
            pid = result.get("id")
            if pid and pid not in seen:
                seen[pid] = result
    return seen.values()


def is_highway_station(station):
    poi = station.get("poi", {})
    address = station.get("address", {})
    name = poi.get("name", "").lower()
    freeform = address.get("freeformAddress", "").lower()
    brands = [b.get("name", "").lower() for b in poi.get("brands", [])]
    brand_names = " ".join(brands)

    highway_keywords = ["aire", "autoroute", "a8", "provençale", "provençale"]
    highway_brands = ["ionity", "totalenergies", "shell recharge", "tesla", "avia"]

    if any(k in name or k in freeform for k in highway_keywords):
        return True
    if any(bk in name or bk in brand_names for bk in highway_brands):
        return True
    return False


def normalize_station(station):
    poi = station.get("poi", {})
    address = station.get("address", {})
    position = station.get("position", {})
    data_sources = station.get("dataSources", {})
    charging_availability = data_sources.get("chargingAvailability", {})
    brands = [b.get("name", "") for b in poi.get("brands", [])]

    return {
        "id": station.get("id"),
        "name": poi.get("name", "N/A"),
        "operator": brands[0] if brands else poi.get("name", "N/A"),
        "address": address.get("freeformAddress", "N/A"),
        "lat": position.get("lat"),
        "lon": position.get("lon"),
        "charging_availability_id": charging_availability.get("id"),
        "has_realtime": charging_availability.get("id") is not None,
    }


def main():
    print(f"Recherche des stations le long de l'A8 (rayon {RADIUS_METERS} m par point)...")
    all_stations = fetch_all_stations()
    print(f"{len(all_stations)} stations trouvées au total.")

    candidates = [s for s in all_stations if is_highway_station(s)]
    normalized = [normalize_station(s) for s in candidates]

    # Tri d'ouest en est (longitude croissante)
    normalized.sort(key=lambda s: s["lon"])

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    realtime_count = sum(1 for s in normalized if s["has_realtime"])
    print(f"{len(normalized)} stations candidates sur autoroute.")
    print(f"{realtime_count} ont un ID de disponibilité temps réel.")
    print(f"Liste écrite dans {OUTPUT_FILE}.")
    print("\nStations avec disponibilité temps réel :")
    for s in normalized:
        if s["has_realtime"]:
            print(f"  - {s['name']} | {s['address']} | {s['lat']},{s['lon']}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""POC : vérifie la disponibilité Chademo des stations TotalEnergies près de Cambarette via TomTom."""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY")
if not TOMTOM_API_KEY:
    print("Erreur : définissez TOMTOM_API_KEY dans .env ou en variable d'environnement.")
    sys.exit(1)

BASE_URL = "https://api.tomtom.com/search/2"

# Aire de Cambarette Nord
TARGET_LAT = 43.423878
TARGET_LON = 5.990385
RADIUS_METERS = 10000  # 10 km autour


def search_totalenergies_stations():
    """Cherche les stations TotalEnergies proches de Cambarette."""
    url = f"{BASE_URL}/nearbySearch/.json"
    params = {
        "key": TOMTOM_API_KEY,
        "lat": TARGET_LAT,
        "lon": TARGET_LON,
        "radius": RADIUS_METERS,
        "limit": 50,
        "categorySet": "7309",  # Electric Vehicle Station
        "brandSet": "TotalEnergies",
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def get_availability(charging_availability_id):
    """Récupère la disponibilité pour le connecteur Chademo."""
    url = f"{BASE_URL}/chargingAvailability.json"
    params = {
        "key": TOMTOM_API_KEY,
        "chargingAvailability": charging_availability_id,
        "connectorSet": "Chademo",
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def extract_chademo_status(availability):
    """Extrait le statut Chademo du payload de disponibilité."""
    for connector in availability.get("connectors", []):
        if connector.get("type") == "Chademo":
            return connector
    return None


def main():
    print(f"Recherche des stations TotalEnergies dans un rayon de {RADIUS_METERS} m autour de Cambarette...")
    search_data = search_totalenergies_stations()
    results = search_data.get("results", [])
    print(f"{len(results)} station(s) TotalEnergies trouvée(s).\n")

    for result in results:
        poi = result.get("poi", {})
        address = result.get("address", {})
        position = result.get("position", {})
        data_sources = result.get("dataSources", {})
        charging_availability = data_sources.get("chargingAvailability", {})
        availability_id = charging_availability.get("id")

        name = poi.get("name", "N/A")
        freeform_address = address.get("freeformAddress", "N/A")

        print(f"Station : {name}")
        print(f"Adresse : {freeform_address}")
        print(f"Position : lat={position.get('lat')}, lon={position.get('lon')}")

        if not availability_id:
            print("  → Aucune donnée de disponibilité temps réel.")
            print()
            continue

        try:
            availability = get_availability(availability_id)
        except requests.HTTPError as exc:
            print(f"  → Erreur lors de la récupération de la disponibilité : {exc}")
            print()
            continue

        chademo = extract_chademo_status(availability)
        if chademo is None:
            print("  → Pas de connecteur Chademo sur cette station.")
            print()
            continue

        current = chademo.get("availability", {}).get("current", {})
        total = chademo.get("total", 0)
        available = current.get("available", 0)
        occupied = current.get("occupied", 0)
        reserved = current.get("reserved", 0)
        unknown = current.get("unknown", 0)
        out_of_service = current.get("outOfService", 0)

        print(f"  Chademo total : {total}")
        print(f"    Disponibles : {available}")
        print(f"    Occupés : {occupied}")
        print(f"    Réservés : {reserved}")
        print(f"    Inconnus : {unknown}")
        print(f"    Hors service : {out_of_service}")

        if available > 0:
            print("  ✅ BORNE CHADEMO DISPONIBLE")
        else:
            print("  ❌ AUCUNE BORNE CHADEMO DISPONIBLE")
        print()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""POC : vérifie la disponibilité Chademo de la borne Ionity Cambarette Nord via TomTom."""

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

# Ionity Cambarette Nord (source : site Ionity)
TARGET_LAT = 43.423878
TARGET_LON = 5.990385
RADIUS_METERS = 1000


def search_station():
    """Cherche les stations de recharge Chademo proches de la cible."""
    url = f"{BASE_URL}/nearbySearch/.json"
    params = {
        "key": TOMTOM_API_KEY,
        "lat": TARGET_LAT,
        "lon": TARGET_LON,
        "radius": RADIUS_METERS,
        "limit": 20,
        "categorySet": "7309",  # Electric Vehicle Station
        "connectorSet": "Chademo",
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def find_ionity_cambarette(results):
    """Retourne la station correspondant à Ionity Cambarette Nord, si présente."""
    for result in results.get("results", []):
        poi = result.get("poi", {})
        name = poi.get("name", "").lower()
        address = result.get("address", {}).get("freeformAddress", "").lower()
        if "ionity" in name or "cambarette" in address:
            return result
    return None


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
    print(f"Recherche des stations Chademo autour de ({TARGET_LAT}, {TARGET_LON})...")
    search_data = search_station()
    results = search_data.get("results", [])
    print(f"{len(results)} résultat(s) trouvé(s).")

    station = find_ionity_cambarette(search_data)

    if station is None:
        print("\nStation Ionity Cambarette non identifiée parmi les résultats.")
        print("Résultats trouvés :")
        for result in results:
            poi = result.get("poi", {})
            address = result.get("address", {})
            print(f"  - {poi.get('name', 'N/A')} | {address.get('freeformAddress', 'N/A')}")
        return

    poi = station.get("poi", {})
    address = station.get("address", {})
    position = station.get("position", {})
    data_sources = station.get("dataSources", {})
    charging_availability = data_sources.get("chargingAvailability", {})
    availability_id = charging_availability.get("id")

    print(f"\nStation identifiée : {poi.get('name', 'N/A')}")
    print(f"Adresse : {address.get('freeformAddress', 'N/A')}")
    print(f"Position : lat={position.get('lat')}, lon={position.get('lon')}")
    print(f"ID disponibilité : {availability_id}")

    if not availability_id:
        print("Aucun ID de disponibilité trouvé pour cette station.")
        return

    print("\nRécupération de la disponibilité Chademo...")
    availability = get_availability(availability_id)
    chademo = extract_chademo_status(availability)

    if chademo is None:
        print("Aucune information de disponibilité Chademo retournée par l'API.")
        return

    current = chademo.get("availability", {}).get("current", {})
    total = chademo.get("total", 0)
    available = current.get("available", 0)
    occupied = current.get("occupied", 0)
    reserved = current.get("reserved", 0)
    unknown = current.get("unknown", 0)
    out_of_service = current.get("outOfService", 0)

    print(f"\nConnecteurs Chademo total : {total}")
    print(f"  Disponibles : {available}")
    print(f"  Occupés : {occupied}")
    print(f"  Réservés : {reserved}")
    print(f"  Inconnus : {unknown}")
    print(f"  Hors service : {out_of_service}")

    if available > 0:
        print("\n✅ Verdict : BORNE CHADEMO DISPONIBLE")
    else:
        print("\n❌ Verdict : AUCUNE BORNE CHADEMO DISPONIBLE")


if __name__ == "__main__":
    main()

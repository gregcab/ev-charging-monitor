#!/usr/bin/env python3
"""Valide les stations candidates en vérifiant qu'elles disposent bien d'un connecteur Chademo.

Génère `stations_validated.json` prêt à être utilisé par le monitoring.
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
INPUT_FILE = "stations_candidates.json"
OUTPUT_FILE = "stations_validated.json"


def get_chademo_availability(charging_availability_id):
    url = f"{BASE_URL}/chargingAvailability.json"
    params = {
        "key": TOMTOM_API_KEY,
        "chargingAvailability": charging_availability_id,
        "connectorSet": "Chademo",
    }
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def extract_chademo(availability):
    for connector in availability.get("connectors", []):
        if connector.get("type") == "Chademo":
            return connector
    return None


def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        candidates = json.load(f)

    validated = []
    for station in candidates:
        avail_id = station.get("charging_availability_id")
        if not avail_id:
            continue

        try:
            availability = get_chademo_availability(avail_id)
        except requests.HTTPError as exc:
            print(f"Erreur pour {station['name']} ({station['address']}) : {exc}")
            continue

        chademo = extract_chademo(availability)
        if chademo is None:
            print(f"Pas de Chademo : {station['name']} | {station['address']}")
            continue

        total = chademo.get("total", 0)
        current = chademo.get("availability", {}).get("current", {})
        available = current.get("available", 0)
        occupied = current.get("occupied", 0)
        out_of_service = current.get("outOfService", 0)

        station["chademo_total"] = total
        station["chademo_available_now"] = available
        station["chademo_occupied_now"] = occupied
        station["chademo_out_of_service_now"] = out_of_service
        validated.append(station)

        status = "✅" if available > 0 else "❌"
        print(f"{status} {station['name']} | {station['address']} | Chademo {available}/{total} dispo")

    validated.sort(key=lambda s: s["lon"])

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(validated, f, ensure_ascii=False, indent=2)

    print(f"\n{len(validated)} station(s) validée(s) avec connecteur Chademo.")
    print(f"Liste écrite dans {OUTPUT_FILE}.")


if __name__ == "__main__":
    main()

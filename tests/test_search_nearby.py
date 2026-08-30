"""Tests de la recherche de stations à proximité (search_nearby).

Aucun appel réseau réel : requests.get est mocké.
"""

import pytest
import requests

from ev_monitor import chargemap_client, dashboard


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _pool(slug, lat, lon, connectors=None):
    return {
        "slug": slug,
        "name": f"Station {slug}",
        "network": {"name": "Opérateur"},
        "street_name": "1 rue de Test",
        "postal_code": "83000",
        "city": "Toulon",
        "gps_coordinates": {"lat": lat, "lon": lon},
        "charging_connectors": (
            connectors if connectors is not None else [{"type": "COMBO_TYPE_2", "count": 4}]
        ),
    }


def _mappy_payload(pools):
    return {
        "response": {
            "content": {
                "count": len(pools),
                "items": [
                    {
                        "lat": pool["gps_coordinates"]["lat"],
                        "lng": pool["gps_coordinates"]["lon"],
                        "pool": pool,
                    }
                    for pool in pools
                ],
            }
        }
    }


def test_search_nearby_filters_and_sends_bbox(monkeypatch):
    # Centre : Toulon (43.12, 5.93) ; une station proche, une lointaine, un cluster.
    near = _pool("station-proche", 43.13, 5.94)
    far = _pool("station-lointaine", 45.75, 4.85)  # Lyon, à ~300 km
    payload = _mappy_payload([far, near])
    # Un cluster (item sans pool) doit être ignoré.
    payload["response"]["content"]["items"].append({"lat": 43.12, "lng": 5.93})

    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return FakeResponse(payload)

    monkeypatch.setattr(chargemap_client.requests, "get", fake_get)

    results = chargemap_client.search_nearby(43.12, 5.93, radius_km=10)

    # La bbox mappy est envoyée via les coins NW/SE au format « lat;lng ».
    assert captured["url"] == chargemap_client.MAPPY_URL
    assert ";" in captured["params"]["NW"]
    assert ";" in captured["params"]["SE"]
    nw_lat, nw_lng = (float(v) for v in captured["params"]["NW"].split(";"))
    se_lat, se_lng = (float(v) for v in captured["params"]["SE"].split(";"))
    assert se_lat < 43.12 < nw_lat
    assert nw_lng < 5.93 < se_lng

    # Seule la station dans le rayon est conservée.
    assert [r["slug"] for r in results] == ["station-proche"]
    assert results[0]["distance_km"] <= 10
    assert results[0]["connectors"] == [{"type": "COMBO_TYPE_2", "count": 4, "power_max": None}]


def test_search_nearby_sorts_by_distance(monkeypatch):
    closest = _pool("station-proche", 43.121, 5.931)
    farthest = _pool("station-plus-loin", 43.15, 5.97)  # ~4,7 km
    payload = _mappy_payload([farthest, closest])
    monkeypatch.setattr(
        chargemap_client.requests, "get",
        lambda *args, **kwargs: FakeResponse(payload),
    )

    results = chargemap_client.search_nearby(43.12, 5.93, radius_km=10)
    assert [r["slug"] for r in results] == ["station-proche", "station-plus-loin"]
    assert results[0]["distance_km"] < results[1]["distance_km"]


def test_search_nearby_network_error(monkeypatch):
    def fake_get(*args, **kwargs):
        raise requests.exceptions.ConnectionError("indisponible")

    monkeypatch.setattr(chargemap_client.requests, "get", fake_get)
    with pytest.raises(RuntimeError):
        chargemap_client.search_nearby(43.12, 5.93)


def test_api_stations_nearby(client, monkeypatch):
    monkeypatch.setattr(
        dashboard, "search_nearby",
        lambda lat, lon, radius_km=10: [{"slug": "station-proche", "distance_km": 1.0}],
    )
    response = client.get("/api/stations/nearby?lat=43.12&lon=5.93&radius=5")
    assert response.status_code == 200
    assert response.get_json()["results"][0]["slug"] == "station-proche"


def test_api_stations_nearby_invalid(client):
    response = client.get("/api/stations/nearby?lat=abc&lon=5.93")
    assert response.status_code == 400
    response = client.get("/api/stations/nearby?lat=43.12&lon=5.93&radius=0")
    assert response.status_code == 400
    response = client.get("/api/stations/nearby?lat=43.12&lon=5.93&radius=500")
    assert response.status_code == 400

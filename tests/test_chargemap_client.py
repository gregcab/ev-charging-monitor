"""Tests du client Chargemap et des nouveaux champs enrichis."""

import pytest

from ev_monitor import chargemap_client


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _pool_detail_payload(**overrides):
    """Payload minimaliste pour pool-detail/v2/pools/{slug}."""
    return {
        "slug": "station-test",
        "name": "Station Test",
        "state": "PUBLISHED",
        "network": {
            "name": "IONITY",
            "logo_url": "https://example.com/logo.png",
        },
        "street_name": "1 rue de Test",
        "postal_code": "75000",
        "city": "Paris",
        "coordinates": {"lat": "48.85", "lon": "2.35"},
        "always_open": True,
        "is_free": False,
        "parking_free": True,
        "indoor": False,
        "is_tesla": False,
        "access": "PUBLIC",
        "location": "HIGHWAY",
        "rating": 4.25,
        "rating_count": 12,
        "description": "Paiement par carte.",
        "amenities": ["restroom", "restoration"],
        "stations": [
            {
                "administrative_state": "in-service",
                "connectors": [
                    {"type": "COMBO_TYPE_2", "power": 350},
                    {"type": "COMBO_TYPE_2", "power": 350},
                    {"type": "CHADEMO", "power": 50},
                ],
            }
        ],
        **overrides,
    }


def test_get_station_info_enriched(monkeypatch):
    payload = _pool_detail_payload()
    monkeypatch.setattr(
        chargemap_client.requests, "get",
        lambda *args, **kwargs: FakeResponse(payload),
    )

    info = chargemap_client.get_station_info("station-test", connector_type="COMBO_TYPE_2")

    assert info["operator"] == "IONITY"
    assert info["operator_logo_url"] == "https://example.com/logo.png"
    assert info["max_power"] == 350
    assert info["chademo_total"] == 2
    assert info["always_open"] is True
    assert info["is_free"] is False
    assert info["parking_free"] is True
    assert info["access"] == "PUBLIC"
    assert info["location"] == "HIGHWAY"
    assert info["rating"] == 4.25
    assert info["rating_count"] == 12
    assert info["amenities"] == ["restroom", "restoration"]
    assert info["description"] == "Paiement par carte."
    assert info["connectors"] == [
        {"type": "CHADEMO", "count": 1, "power_max": 50},
        {"type": "COMBO_TYPE_2", "count": 2, "power_max": 350},
    ]


def test_get_station_info_max_power_for_connector(monkeypatch):
    payload = _pool_detail_payload()
    monkeypatch.setattr(
        chargemap_client.requests, "get",
        lambda *args, **kwargs: FakeResponse(payload),
    )

    info_chademo = chargemap_client.get_station_info("station-test", connector_type="CHADEMO")
    assert info_chademo["max_power"] == 50
    assert info_chademo["chademo_total"] == 1


def test_search_by_name_filters_only_published(monkeypatch):
    payload = {
        "items": [
            {"slug": "published", "name": "Publiée", "state": "PUBLISHED", "stations": []},
            {"slug": "deleted", "name": "Supprimée", "state": "DELETED", "stations": []},
            {"slug": "creating", "name": "En création", "state": "CREATING", "stations": []},
        ]
    }
    monkeypatch.setattr(
        chargemap_client.requests, "get",
        lambda *args, **kwargs: FakeResponse(payload),
    )

    results = chargemap_client._search_by_name("test")
    assert [r["slug"] for r in results] == ["published"]


def test_search_by_city_returns_enriched_fields(monkeypatch):
    payload = {
        "response": {
            "content": {
                "count": 1,
                "items": [
                    {
                        "lat": 43.12,
                        "lng": 5.93,
                        "pool": {
                            "slug": "station-mappy",
                            "name": "Station Mappy",
                            "network": {"name": "OpA", "logo_url": "https://example.com/opA.png"},
                            "street_name": "Rue Mappy",
                            "postal_code": "83000",
                            "city": "Toulon",
                            "gps_coordinates": {"lat": 43.12, "lon": 5.93},
                            "charging_connectors": [
                                {"type": "COMBO_TYPE_2", "count": 2, "power_max": 150},
                            ],
                            "operational_status": "OPERATIONAL",
                            "availability_status": "AVAILABLE",
                            "real_time_available": True,
                            "is_always_open": True,
                            "is_free": False,
                            "is_tesla": False,
                            "amenities": ["restroom"],
                            "rating": 4.0,
                            "rating_count": 5,
                        },
                    }
                ],
            }
        }
    }
    monkeypatch.setattr(
        chargemap_client.requests, "get",
        lambda *args, **kwargs: FakeResponse(payload),
    )

    results = chargemap_client._search_by_city("Toulon")
    assert len(results) == 1
    result = results[0]
    assert result["slug"] == "station-mappy"
    assert result["operator_logo_url"] == "https://example.com/opA.png"
    assert result["power_max"] == 150
    assert result["operational_status"] == "OPERATIONAL"
    assert result["availability_status"] == "AVAILABLE"
    assert result["real_time_available"] is True
    assert result["always_open"] is True
    assert result["amenities"] == ["restroom"]
    assert result["rating"] == 4.0
    assert result["connectors"] == [{"type": "COMBO_TYPE_2", "count": 2, "power_max": 150}]

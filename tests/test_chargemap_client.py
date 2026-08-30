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


def test_get_station_detail_maps_connectors_and_monitored_flag(monkeypatch):
    payload = _pool_detail_payload(
        stations=[
            {
                "id": 101,
                "label": "Borne A",
                "administrative_state": "in-service",
                "connectors": [
                    {
                        "id": 1001,
                        "type": "COMBO_TYPE_2",
                        "power": 350,
                        "voltage": 900,
                        "intensity": 500,
                        "current_type": "DC",
                        "realtime_state": "AVAILABLE",
                        "is_bookable": True,
                        "evse_id": "FR*AAA*E123",
                        "is_remote_charge_compatible": True,
                        "is_auto_charge_compatible": False,
                        "is_plug_and_charge_compatible": True,
                    },
                    {
                        "id": 1002,
                        "type": "CHADEMO",
                        "power": 50,
                        "realtime_state": "BUSY",
                        "is_bookable": False,
                    },
                ],
            }
        ]
    )
    monkeypatch.setattr(
        chargemap_client.requests, "get",
        lambda *args, **kwargs: FakeResponse(payload),
    )

    detail = chargemap_client.get_station_detail("station-test", connector_type="COMBO_TYPE_2")
    assert len(detail["stations"]) == 1
    station = detail["stations"][0]
    assert station["id"] == 101
    assert station["label"] == "Borne A"

    combo = station["connectors"][0]
    assert combo["type"] == "COMBO_TYPE_2"
    assert combo["power"] == 350
    assert combo["voltage"] == 900
    assert combo["intensity"] == 500
    assert combo["current_type"] == "DC"
    assert combo["state"] == "available"
    assert combo["raw_state"] == "AVAILABLE"
    assert combo["is_bookable"] is True
    assert combo["evse_id"] == "FR*AAA*E123"
    assert combo["is_remote_charge_compatible"] is True
    assert combo["is_plug_and_charge_compatible"] is True
    assert combo["is_monitored"] is True

    chademo = station["connectors"][1]
    assert chademo["state"] == "busy"
    assert chademo["is_monitored"] is False


def test_get_station_info_owner_passes_statistic(monkeypatch):
    payload = _pool_detail_payload(
        owner={"name": "Owner Corp", "website": "https://owner.example.com"},
        should_check_prices=True,
        schedules=["Lun-Ven 08h-22h", "Sam-Dim 09h-20h"],
        avatar_url="https://example.com/avatar.png",
        cover_url="https://example.com/cover.png",
        statistic={
            "checkins_count": 42,
            "comments_count": 7,
            "material_note_average": 4.5,
            "price_note_average": 3.0,
        },
        stations=[
            {
                "administrative_state": "in-service",
                "authentication_methods": ["app", "rfid"],
                "highlighted_passes": [{"id": 1, "name": "Pass Premium"}],
                "third_party_passes": [{"id": 2, "name": "Pass Premium"}, {"id": 3, "name": "Autre Pass"}],
                "connectors": [{"type": "COMBO_TYPE_2", "power": 350}],
            }
        ],
    )
    monkeypatch.setattr(
        chargemap_client.requests, "get",
        lambda *args, **kwargs: FakeResponse(payload),
    )

    info = chargemap_client.get_station_info("station-test", connector_type="COMBO_TYPE_2")
    assert info["owner_name"] == "Owner Corp"
    assert info["owner_website"] == "https://owner.example.com"
    assert info["should_check_prices"] is True
    assert info["schedules"] == ["Lun-Ven 08h-22h", "Sam-Dim 09h-20h"]
    assert info["avatar_url"] == "https://example.com/avatar.png"
    assert info["cover_url"] == "https://example.com/cover.png"
    assert info["statistic"]["checkins_count"] == 42
    assert info["authentication_methods"] == ["app", "rfid"]
    assert info["passes"] == [
        {"id": 1, "name": "Pass Premium", "highlighted": True},
        {"id": 3, "name": "Autre Pass", "highlighted": False},
    ]


def test_pool_to_result_normalizes_speed_and_location():
    result = chargemap_client._pool_to_result(
        {
            "slug": "s",
            "name": "S",
            "coordinates": {"lat": 43.0, "lon": 6.0},
            "speed": {"id": "FAST", "label": "Rapide"},
            "location": "HIGHWAY",
        }
    )
    assert result["speed"] == "FAST"
    assert result["location"] == "HIGHWAY"

    result2 = chargemap_client._pool_to_result(
        {"slug": "s2", "name": "S2", "coordinates": {"lat": 44.0, "lon": 7.0}}
    )
    assert result2["speed"] is None
    assert result2["location"] is None

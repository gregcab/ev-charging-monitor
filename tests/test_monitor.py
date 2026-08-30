"""Tests du scheduler de collecte : jitter, espacement et backoff."""

import random
import time

import pytest

from ev_monitor import monitor
from ev_monitor.chargemap_client import get_charging_availability


def test_jittered_interval_range(monkeypatch):
    """Le jitter retourne un intervalle centré sur la valeur de base."""
    monkeypatch.setattr(random, "uniform", lambda a, b: 1.0)
    assert monitor._jittered_interval(5) == 5
    monkeypatch.setattr(random, "uniform", lambda a, b: 0.8)
    assert monitor._jittered_interval(5) == 4
    monkeypatch.setattr(random, "uniform", lambda a, b: 1.4)
    assert monitor._jittered_interval(5) == 7
    # Minimum 1 minute même avec un jitter fort vers le bas
    monkeypatch.setattr(random, "uniform", lambda a, b: 0.1)
    assert monitor._jittered_interval(5) == 1


def test_collect_once_pauses_between_requests(monkeypatch, seeded_db):
    """Les requêtes sont espacées d'une pause aléatoire."""
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(random, "uniform", lambda a, b: 3.0)
    monkeypatch.setattr(
        monitor,
        "get_charging_availability",
        lambda slug, connector_type: {
            "availability": {"current": {"available": 1, "occupied": 0, "reserved": 0, "unknown": 0, "outOfService": 0}},
            "total": 1,
        },
    )

    monitor._consecutive_errors.clear()
    monitor.collect_once()

    # 3 stations -> 2 pauses (la première est immédiate)
    assert len(sleeps) == 2
    assert all(s == 3.0 for s in sleeps)


def test_collect_once_backoff_skips_station(monkeypatch, seeded_db):
    """Une station avec 3 erreurs consécutives est ignorée."""
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(random, "uniform", lambda a, b: 3.0)

    calls = []

    def fake_availability(slug, connector_type):
        calls.append(slug)
        raise RuntimeError("Chargemap indisponible")

    monkeypatch.setattr(monitor, "get_charging_availability", fake_availability)

    monitor._consecutive_errors.clear()

    # Deux premiers cycles : toutes les stations sont interrogées.
    monitor.collect_once()
    assert len(calls) == 3
    monitor.collect_once()
    assert len(calls) == 6

    # Troisième cycle : les stations atteignent 3 erreurs consécutives.
    monitor.collect_once()
    assert len(calls) == 9

    # Quatrième cycle : toutes les stations sont en backoff, aucune requête.
    monitor.collect_once()
    assert len(calls) == 9


def test_collect_once_resets_error_count_on_success(monkeypatch, seeded_db):
    """Le compteur d'erreurs est réinitialisé après un succès."""
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(random, "uniform", lambda a, b: 3.0)

    monitor._consecutive_errors.clear()
    monitor._consecutive_errors["station-paris-1"] = 2

    monkeypatch.setattr(
        monitor,
        "get_charging_availability",
        lambda slug, connector_type: {
            "availability": {"current": {"available": 1, "occupied": 0, "reserved": 0, "unknown": 0, "outOfService": 0}},
            "total": 1,
        },
    )

    monitor.collect_once()
    assert monitor._consecutive_errors["station-paris-1"] == 0


def test_collect_once_full_error_cycles(monkeypatch, seeded_db):
    """Un cycle complet en erreur incrémente le compteur global."""
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(random, "uniform", lambda a, b: 3.0)
    monkeypatch.setattr(
        monitor,
        "get_charging_availability",
        lambda slug, connector_type: (_ for _ in ()).throw(RuntimeError("down")),
    )

    monitor._consecutive_errors.clear()
    monitor._full_error_cycles = 0

    monitor.collect_once()
    assert monitor._full_error_cycles == 1
    monitor.collect_once()
    assert monitor._full_error_cycles == 2

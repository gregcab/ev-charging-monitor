"""Tests des filtres Jinja2 personnalisés du dashboard."""

from datetime import datetime, timezone

from ev_monitor.chargemap_client import DEFAULT_CONNECTOR_TYPE, connector_label
from ev_monitor.dashboard import connector_label_filter, fr_datetime


def test_fr_datetime_utc():
    dt = datetime(2024, 1, 15, 14, 30, tzinfo=timezone.utc)
    assert fr_datetime(dt.isoformat()) == "15/01 15:30"


def test_fr_datetime_naive():
    dt = datetime(2024, 1, 15, 14, 30)
    assert fr_datetime(dt.isoformat()) == "15/01 15:30"


def test_fr_datetime_none():
    assert fr_datetime(None) is None


def test_connector_label_known():
    assert connector_label("CHADEMO") == "Chademo"
    assert connector_label("COMBO_TYPE_2") == "Combo CCS"
    assert connector_label("MENNEKES_TYPE_2") == "Type 2"


def test_connector_label_unknown():
    assert connector_label("UNKNOWN_TYPE") == "UNKNOWN_TYPE"


def test_connector_label_filter():
    assert connector_label_filter(None) == "Chademo"
    assert connector_label_filter("COMBO_TYPE_2") == "Combo CCS"


def test_connector_label_default():
    """Le connecteur par défaut (env/défaut embarqué) a un libellé connu."""
    assert connector_label(DEFAULT_CONNECTOR_TYPE) == "Chademo"

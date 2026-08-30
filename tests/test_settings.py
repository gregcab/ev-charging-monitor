"""Tests des préférences (table settings) et de la gestion des trajets."""

import pytest

from ev_monitor import storage


def test_get_settings_empty(seeded_db):
    assert storage.get_settings() == {}


def test_save_and_get_settings(seeded_db):
    storage.save_settings({"app_name": "Mon EV", "monitor_interval_minutes": 15})
    assert storage.get_settings() == {
        "app_name": "Mon EV",
        "monitor_interval_minutes": "15",
    }
    # Écrasement d'une clé existante
    storage.save_settings({"app_name": "Autre nom"})
    assert storage.get_settings()["app_name"] == "Autre nom"
    # None supprime la clé
    storage.save_settings({"app_name": None})
    assert "app_name" not in storage.get_settings()


def test_effective_settings_defaults(seeded_db):
    """Sans valeur en base, les préférences retombent sur l'env/défaut."""
    settings = storage.get_effective_settings()
    assert settings["app_name"] == storage.APP_NAME
    assert settings["app_subtitle"] == storage.APP_SUBTITLE
    assert settings["default_connector_type"] == storage.DEFAULT_CONNECTOR_TYPE
    assert settings["monitor_interval_minutes"] == storage.MONITOR_INTERVAL_MINUTES


def test_effective_settings_db_overrides_env(seeded_db, monkeypatch):
    """Priorité : valeur en base > variable d'env > défaut embarqué."""
    monkeypatch.setattr(storage, "APP_NAME", "Nom env")
    monkeypatch.setattr(storage, "MONITOR_INTERVAL_MINUTES", 9)
    # Sans valeur en base : l'env gagne
    settings = storage.get_effective_settings()
    assert settings["app_name"] == "Nom env"
    assert settings["monitor_interval_minutes"] == 9
    # La valeur en base gagne sur l'env
    storage.save_settings({"app_name": "Nom base", "monitor_interval_minutes": 3})
    settings = storage.get_effective_settings()
    assert settings["app_name"] == "Nom base"
    assert settings["monitor_interval_minutes"] == 3


def test_reset_settings(seeded_db):
    storage.save_settings({"app_name": "Nom base", "default_connector_type": "COMBO_TYPE_2"})
    storage.reset_settings()
    assert storage.get_settings() == {}
    settings = storage.get_effective_settings()
    assert settings["app_name"] == storage.APP_NAME
    assert settings["default_connector_type"] == storage.DEFAULT_CONNECTOR_TYPE


def test_api_settings_save(client):
    response = client.post("/api/settings", json={
        "app_name": "Mon App",
        "app_subtitle": "Mes bornes",
        "default_connector_type": "COMBO_TYPE_2",
        "monitor_interval_minutes": 10,
    })
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["settings"]["app_name"] == "Mon App"
    assert data["settings"]["monitor_interval_minutes"] == 10
    # Le nom est pris en compte à chaud dans les templates.
    html = client.get("/").data.decode("utf-8")
    assert "<h1>Mon App</h1>" in html


def test_api_settings_invalid_interval(client):
    response = client.post("/api/settings", json={"monitor_interval_minutes": 0})
    assert response.status_code == 400
    response = client.post("/api/settings", json={"monitor_interval_minutes": "abc"})
    assert response.status_code == 400


def test_api_settings_unknown_connector(client):
    response = client.post("/api/settings", json={"default_connector_type": "INCONNU"})
    assert response.status_code == 400


def test_api_settings_reset(client):
    client.post("/api/settings", json={"app_name": "Temporaire"})
    response = client.post("/api/settings/reset")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["settings"]["app_name"] == storage.APP_NAME


def test_get_trajets(seeded_db):
    trajets = storage.get_trajets()
    assert trajets == [{"name": "Paris → Lyon", "station_count": 2}]


def test_rename_trajet(seeded_db):
    updated = storage.rename_trajet("Paris → Lyon", "Paris → Marseille")
    assert updated == 2
    # JSON mis à jour
    stations = {s["id"]: s for s in storage.load_stations_from_json()}
    assert stations["station-paris-1"]["direction"] == "Paris → Marseille"
    assert stations["station-paris-2"]["direction"] == "Paris → Marseille"
    assert stations["station-lyon-1"]["direction"] is None
    # Base resynchronisée
    db_stations = {s["id"]: s for s in storage.get_all_stations()}
    assert db_stations["station-paris-1"]["direction"] == "Paris → Marseille"
    assert storage.get_trajets() == [{"name": "Paris → Marseille", "station_count": 2}]


def test_rename_trajet_merge(seeded_db):
    """Renommer vers un trajet existant fusionne les deux trajets."""
    storage.update_station("station-lyon-1", {"direction": "Sud"})
    updated = storage.rename_trajet("Paris → Lyon", "Sud")
    assert updated == 2
    assert storage.get_trajets() == [{"name": "Sud", "station_count": 3}]


def test_rename_trajet_unknown(seeded_db):
    with pytest.raises(ValueError):
        storage.rename_trajet("Inconnu", "Autre")


def test_delete_trajet(seeded_db):
    updated = storage.delete_trajet("Paris → Lyon")
    assert updated == 2
    # Les stations passent à « sans trajet » sans être supprimées.
    stations = {s["id"]: s for s in storage.load_stations_from_json()}
    assert stations["station-paris-1"]["direction"] is None
    assert stations["station-paris-2"]["direction"] is None
    db_stations = {s["id"]: s for s in storage.get_all_stations()}
    assert db_stations["station-paris-2"]["direction"] is None
    assert len(db_stations) == 3
    assert storage.get_trajets() == []


def test_delete_trajet_unknown(seeded_db):
    with pytest.raises(ValueError):
        storage.delete_trajet("Inconnu")


def test_api_trajets_rename(client):
    response = client.post(
        "/api/trajets/rename", json={"old": "Paris → Lyon", "new": "A8"}
    )
    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "updated": 2}
    html = client.get("/").data.decode("utf-8")
    assert ">A8</span>" in html


def test_api_trajets_rename_invalid(client):
    response = client.post("/api/trajets/rename", json={"old": "", "new": "X"})
    assert response.status_code == 400
    response = client.post("/api/trajets/rename", json={"old": "Inconnu", "new": "X"})
    assert response.status_code == 400


def test_api_trajets_delete(client):
    response = client.post("/api/trajets/delete", json={"name": "Paris → Lyon"})
    assert response.status_code == 200
    assert response.get_json()["updated"] == 2
    assert storage.get_trajets() == []


def test_api_trajets_delete_invalid(client):
    response = client.post("/api/trajets/delete", json={})
    assert response.status_code == 400
    response = client.post("/api/trajets/delete", json={"name": "Inconnu"})
    assert response.status_code == 400


def test_effective_settings_show_station_details_default(seeded_db, monkeypatch):
    """show_station_details est False par défaut (env/défaut)."""
    monkeypatch.setattr(storage, "SHOW_STATION_DETAILS", False)
    assert storage.get_effective_settings()["show_station_details"] is False


def test_effective_settings_show_station_details_env(seeded_db, monkeypatch):
    """La variable d'environnement peut activer les détails par défaut."""
    monkeypatch.setattr(storage, "SHOW_STATION_DETAILS", True)
    assert storage.get_effective_settings()["show_station_details"] is True


def test_effective_settings_show_station_details_db_overrides(seeded_db, monkeypatch):
    """La valeur en base l'emporte sur l'environnement."""
    monkeypatch.setattr(storage, "SHOW_STATION_DETAILS", True)
    storage.save_settings({"show_station_details": False})
    assert storage.get_effective_settings()["show_station_details"] is False
    storage.save_settings({"show_station_details": True})
    assert storage.get_effective_settings()["show_station_details"] is True


def test_api_settings_show_station_details(client):
    response = client.post("/api/settings", json={"show_station_details": True})
    assert response.status_code == 200
    data = response.get_json()
    assert data["settings"]["show_station_details"] is True
    # La page Paramètres reflète le setting.
    html = client.get("/parametres").data.decode("utf-8")
    assert 'id="prefShowDetails" checked' in html
    # Réinitialisation
    client.post("/api/settings/reset")
    assert storage.get_effective_settings()["show_station_details"] is False

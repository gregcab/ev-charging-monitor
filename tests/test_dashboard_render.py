"""Tests du rendu HTML des pages du dashboard."""

import re


def test_index_renders_200(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    # Le titre vient des préférences effectives (APP_NAME par défaut).
    assert "<title>EV Charging Monitor</title>" in html
    assert "<h1>EV Charging Monitor</h1>" in html
    assert "Disponibilité des bornes de recharge" in html
    assert "Station Paris 1" in html
    assert "Station Paris 2" in html
    assert "Station Lyon 1" in html


def test_index_stats(client):
    response = client.get("/")
    html = response.data.decode("utf-8")
    # 3 stations, 7 bornes au total (2 + 1 + 4), 6 dispo, 1 station à 0.
    assert re.search(r'<div class="label">Stations</div>\s*<div class="value">3</div>', html)
    assert re.search(r'<div class="label">Bornes suivies</div>\s*<div class="value">7</div>', html)
    assert re.search(r'<div class="label">Disponibles maintenant</div>\s*<div class="value text-green">6</div>', html)
    assert re.search(r'<div class="label">Stations à 0 dispo</div>\s*<div class="value text-red">1</div>', html)


def test_index_order(client):
    """Le tableau doit être trié par trajet, display_order, puis longitude.

    Les stations sans trajet sont affichées à la fin.
    """
    response = client.get("/")
    html = response.data.decode("utf-8")
    # Paris → Lyon : station-paris-2 (order 0) puis station-paris-1 (order 1)
    # Sans trajet : station-lyon-1, en dernier
    pos_paris_2 = html.find("Station Paris 2")
    pos_paris_1 = html.find("Station Paris 1")
    pos_lyon_1 = html.find("Station Lyon 1")
    assert 0 < pos_paris_2 < pos_paris_1
    assert 0 < pos_paris_1 < pos_lyon_1


def test_index_generic_trajet_badge(client):
    """Les trajets utilisent un badge générique, sans style propre à un axe."""
    response = client.get("/")
    html = response.data.decode("utf-8")
    assert "badge-aix-nice" not in html
    assert "badge-nice-aix" not in html
    assert 'class="badge badge-trajet">Paris → Lyon</span>' in html


def test_index_trajet_datalist(client):
    """Les formulaires proposent les trajets existants via une datalist."""
    response = client.get("/")
    html = response.data.decode("utf-8")
    assert '<datalist id="trajetsList">' in html
    assert '<option value="Paris → Lyon"></option>' in html
    assert 'id="stationDirection" list="trajetsList"' in html
    assert 'id="editStationDirection" list="trajetsList"' in html


def test_index_default_connector_js(client):
    """La préférence de connecteur JS utilise le connecteur par défaut effectif."""
    response = client.get("/")
    html = response.data.decode("utf-8")
    assert 'const DEFAULT_CONNECTOR_TYPE = "CHADEMO";' in html


def test_index_nav_links(client):
    """La navigation principale contient les liens Carte et Paramètres."""
    response = client.get("/")
    html = response.data.decode("utf-8")
    assert 'href="/carte"' in html
    assert 'href="/parametres"' in html


def _extract_row(html, station_name):
    """Extrait la balise <tr> complète contenant le nom d'une station."""
    idx = html.find(station_name)
    assert idx > 0
    start = html.rfind("<tr>", 0, idx)
    end = html.find("</tr>", idx) + len("</tr>")
    return html[start:end]


def test_index_availability_colors(client):
    response = client.get("/")
    html = response.data.decode("utf-8")
    # Station Paris 1 est à 2/2 dispo -> vert ; Paris 2 à 0/1 -> orange (occupied > 0)
    paris_1_row = _extract_row(html, "Station Paris 1")
    paris_2_row = _extract_row(html, "Station Paris 2")
    assert "dot-green" in paris_1_row
    assert "dot-orange" in paris_2_row
    assert "text-green" in paris_1_row
    assert "text-orange" in paris_2_row
    # Vérification des barres de progression
    assert "availability-bar-green" in paris_1_row
    assert "availability-bar-orange" in paris_2_row
    assert 'style="width: 100%;"' in paris_1_row
    assert 'style="width: 0%;"' in paris_2_row


def test_status_banner(client):
    """Le bandeau d'état global affiche l'état de la dernière collecte."""
    response = client.get("/")
    html = response.data.decode("utf-8")
    assert "status-banner" in html
    assert "status-ok" in html
    assert "Dernière collecte OK" in html


def test_station_detail_renders_200(client):
    response = client.get("/station/station-paris-1")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Station Paris 1" in html
    assert "Adresse A" in html


def test_station_detail_404(client):
    response = client.get("/station/inexistante")
    assert response.status_code == 404
    assert "Station non trouvée" in response.data.decode("utf-8")


def test_aide_renders_200(client):
    response = client.get("/aide")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Aide" in html
    assert "Rafraîchissement automatique" not in html


def test_logs_renders_200(client):
    response = client.get("/logs")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Logs d'erreur" in html
    assert "EV Charging Monitor" in html


def test_carte_renders_200(client):
    """La page carte affiche le conteneur Leaflet et charge les stations via l'API."""
    response = client.get("/carte")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert 'id="map"' in html
    assert "leaflet" in html.lower()
    assert "/api/stations/nearby" in html
    assert "EV Charging Monitor" in html


def test_parametres_renders_200(client):
    """La page paramètres affiche les sections Trajets et Préférences."""
    response = client.get("/parametres")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Trajets" in html
    assert "Préférences" in html
    assert "Paris → Lyon" in html
    assert "/api/trajets/rename" in html
    assert "/api/trajets/delete" in html
    assert "/api/settings" in html


def test_index_reliability_table(client):
    """La section fiabilité 30 jours est présente et charge ses données via l’API."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Fiabilité des stations" in html
    assert 'id="reliabilityTable"' in html
    assert 'id="reliabilityBody"' in html
    assert "/api/stations/stats?hours=168" in html
    assert "/api/stations/stats?hours=720" in html


def test_station_detail_heatmap(client):
    """La page de détail expose la heatmap des créneaux de disponibilité."""
    response = client.get("/station/station-paris-1")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Créneaux de disponibilité" in html
    assert 'id="heatmapChart"' in html
    assert 'id="heatmapCard"' in html
    assert "/api/heatmap/${stationId}" in html

"""Tests du rendu HTML des pages du dashboard."""

import re


def test_index_renders_200(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Surveillance Chademo A8" in html
    assert "Station Aix 1" in html
    assert "Station Aix 2" in html
    assert "Station Nice 1" in html


def test_index_stats(client):
    response = client.get("/")
    html = response.data.decode("utf-8")
    # 3 stations, 7 bornes au total (2 + 1 + 4), 6 dispo, 1 station à 0.
    assert re.search(r'<div class="label">Stations</div>\s*<div class="value">3</div>', html)
    assert re.search(r'<div class="label">Bornes suivies</div>\s*<div class="value">7</div>', html)
    assert re.search(r'<div class="label">Disponibles maintenant</div>\s*<div class="value text-green">6</div>', html)
    assert re.search(r'<div class="label">Stations à 0 dispo</div>\s*<div class="value text-red">1</div>', html)


def test_index_order(client):
    """Le tableau doit être trié par sens, display_order, puis longitude."""
    response = client.get("/")
    html = response.data.decode("utf-8")
    # Aix → Nice : station-aix-2 (order 0, lon 6.0) puis station-aix-1 (order 1, lon 5.9)
    # Nice → Aix : station-nice-1
    pos_aix_2 = html.find("Station Aix 2")
    pos_aix_1 = html.find("Station Aix 1")
    pos_nice_1 = html.find("Station Nice 1")
    assert 0 < pos_aix_2 < pos_aix_1
    assert 0 < pos_aix_1 < pos_nice_1


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
    # Station Aix 1 est à 2/2 dispo -> vert ; Aix 2 à 0/1 -> orange (occupied > 0)
    aix_1_row = _extract_row(html, "Station Aix 1")
    aix_2_row = _extract_row(html, "Station Aix 2")
    assert "dot-green" in aix_1_row
    assert "dot-orange" in aix_2_row
    assert "text-green" in aix_1_row
    assert "text-red" in aix_2_row


def test_station_detail_renders_200(client):
    response = client.get("/station/station-aix-1")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Station Aix 1" in html
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

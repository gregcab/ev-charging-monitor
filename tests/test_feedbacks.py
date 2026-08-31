"""Tests de la collecte et de la recherche de feedbacks."""

from unittest.mock import patch

import pytest

from ev_monitor import chargemap_client, storage
from ev_monitor.dashboard import app


SAMPLE_FEEDBACK_RESPONSE = {
    "items": [
        {
            "id": 1001,
            "type": "COMMENT",
            "user_username": "user_a",
            "creation_date": "2026-08-30T14:00:00+00:00",
            "comment": "Borne rapide et propre",
            "chargemap_response": None,
            "reason_type": None,
            "sentiment": "POSITIVE",
            "locale": "fr_FR",
        },
        {
            "id": 1002,
            "type": "REPORT",
            "user_username": "user_b",
            "creation_date": "2026-08-29T10:00:00+00:00",
            "comment": None,
            "rating": {
                "comment": "Borne en panne depuis plusieurs jours",
                "sentiment": "NEGATIVE",
            },
            "chargemap_response": {
                "public_content": "Merci pour le signalement",
            },
            "reason_type": "OUT_OF_ORDER",
            "sentiment": None,
            "locale": "fr_FR",
        },
    ]
}


def test_get_pool_feedbacks_paginates(monkeypatch):
    calls = []

    def fake_get(url, params, timeout):
        calls.append(params)
        class Resp:
            def raise_for_status(self): pass
            def json(self): return SAMPLE_FEEDBACK_RESPONSE
        return Resp()

    monkeypatch.setattr(chargemap_client.requests, "get", fake_get)
    feedbacks = chargemap_client.get_pool_feedbacks(131293, limit=2)

    assert len(feedbacks) == 2
    assert feedbacks[0]["feedback_id"] == 1001
    assert feedbacks[0]["content"] == "Borne rapide et propre"
    assert feedbacks[1]["feedback_id"] == 1002
    assert feedbacks[1]["content"] == "Borne en panne depuis plusieurs jours"
    assert feedbacks[1]["response_content"] == "Merci pour le signalement"
    assert calls[0]["pool_id"] == 131293
    assert calls[0]["offset"] == 0


def test_save_and_search_feedbacks(client, seeded_db):
    storage.save_feedbacks("station-paris-1", [
        {
            "feedback_id": 2001,
            "type": "COMMENT",
            "username": "u1",
            "created_at": "2026-08-30T14:00:00+00:00",
            "content": "Borne rapide et propre",
            "response_content": "",
            "reason_type": None,
            "sentiment": "POSITIVE",
            "locale": "fr_FR",
        },
        {
            "feedback_id": 2002,
            "type": "REPORT",
            "username": "u2",
            "created_at": "2026-08-29T10:00:00+00:00",
            "content": "Borne en panne depuis plusieurs jours",
            "response_content": "Merci",
            "reason_type": "OUT_OF_ORDER",
            "sentiment": "NEGATIVE",
            "locale": "fr_FR",
        },
    ])

    results = storage.search_feedbacks("panne")
    assert len(results) == 1
    assert results[0]["feedback_id"] == 2002

    results = storage.search_feedbacks("", types=["COMMENT"])
    assert len(results) == 1
    assert results[0]["feedback_id"] == 2001

    results = storage.search_feedbacks("", sentiments=["NEGATIVE"])
    assert len(results) == 1
    assert results[0]["feedback_id"] == 2002

    counts = storage.get_feedback_counts()
    assert counts["total"] == 2


def test_feedbacks_page_renders(client):
    response = client.get("/feedbacks")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Feedbacks" in html
    assert "feedbacks-search" in html or "feedback-search" in html


def test_api_feedbacks_search(client, seeded_db):
    storage.save_feedbacks("station-paris-1", [
        {
            "feedback_id": 3001,
            "type": "COMMENT",
            "username": "u1",
            "created_at": "2026-08-30T14:00:00+00:00",
            "content": "Très bonne station",
            "response_content": "",
            "reason_type": None,
            "sentiment": "POSITIVE",
            "locale": "fr_FR",
        },
    ])

    response = client.get("/api/feedbacks/search?q=bonne")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["feedbacks"]) == 1
    assert data["feedbacks"][0]["feedback_id"] == 3001
    assert data["counts"]["total"] == 1


def test_api_feedbacks_stats(client, seeded_db):
    storage.save_feedbacks("station-paris-2", [
        {
            "feedback_id": 4001,
            "type": "CHECKIN",
            "username": "u1",
            "created_at": "2026-08-30T14:00:00+00:00",
            "content": "",
            "response_content": "",
            "reason_type": None,
            "sentiment": None,
            "locale": "fr_FR",
        },
    ])
    response = client.get("/api/feedbacks/stats")
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] >= 1

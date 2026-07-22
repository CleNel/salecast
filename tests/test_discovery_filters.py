import sqlite3
from datetime import date

import pytest

from salecast import db, discovery


def test_months_since_recent_release():
    assert discovery.months_since("2026-06-12", today=date(2026, 7, 12)) == pytest.approx(1.0, abs=0.1)


def test_months_since_old_release():
    assert discovery.months_since("2020-01-01", today=date(2026, 7, 12)) > 60


def test_months_since_future_release_is_negative():
    assert discovery.months_since("2026-12-01", today=date(2026, 7, 12)) < 0


def test_enrich_and_filter_excludes_non_games(monkeypatch):
    def fake_batch(app_ids, delay_sec=0):
        for app_id in app_ids:
            yield app_id, {
                "type": "dlc",
                "is_released": True,
                "release_date": "2020-01-01",
                "name": "Some DLC",
                "genre": "Action",
                "publisher": "Pub",
                "review_count": 1000,
            }

    monkeypatch.setattr(
        "salecast.clients.steam_client.rate_limited_appdetails_batch", fake_batch
    )
    survivors = discovery.enrich_and_filter_candidates({1}, min_age_months=6)
    assert survivors == []


def test_enrich_and_filter_excludes_free_to_play_games(monkeypatch):
    def fake_batch(app_ids, delay_sec=0):
        for app_id in app_ids:
            yield app_id, {
                "type": "game",
                "is_released": True,
                "is_free": True,
                "release_date": "2020-01-01",
                "name": "Free Game",
                "genre": "Action",
                "publisher": "Pub",
                "review_count": 100000,
            }

    monkeypatch.setattr(
        "salecast.clients.steam_client.rate_limited_appdetails_batch", fake_batch
    )
    survivors = discovery.enrich_and_filter_candidates({1}, min_age_months=6)
    assert survivors == []


def test_enrich_and_filter_excludes_too_young(monkeypatch):
    def fake_batch(app_ids, delay_sec=0):
        for app_id in app_ids:
            yield app_id, {
                "type": "game",
                "is_released": True,
                "release_date": date.today().isoformat(),
                "name": "Brand New Game",
                "genre": "Action",
                "publisher": "Pub",
                "review_count": 1000,
            }

    monkeypatch.setattr(
        "salecast.clients.steam_client.rate_limited_appdetails_batch", fake_batch
    )
    survivors = discovery.enrich_and_filter_candidates({1}, min_age_months=6)
    assert survivors == []


def test_enrich_and_filter_keeps_qualifying_game(monkeypatch):
    def fake_batch(app_ids, delay_sec=0):
        for app_id in app_ids:
            yield app_id, {
                "type": "game",
                "is_released": True,
                "release_date": "2020-01-01",
                "name": "Old Good Game",
                "genre": "RPG",
                "publisher": "Pub",
                "review_count": 5000,
            }

    monkeypatch.setattr(
        "salecast.clients.steam_client.rate_limited_appdetails_batch", fake_batch
    )
    survivors = discovery.enrich_and_filter_candidates({42}, min_age_months=6)
    assert len(survivors) == 1
    assert survivors[0]["app_id"] == 42
    assert survivors[0]["name"] == "Old Good Game"


def test_enrich_and_filter_stops_early_at_target_count(monkeypatch):
    processed_ids = []

    def fake_batch(app_ids, delay_sec=0):
        for app_id in app_ids:
            processed_ids.append(app_id)
            yield app_id, {
                "type": "game",
                "is_released": True,
                "release_date": "2020-01-01",
                "name": f"Game {app_id}",
                "genre": "RPG",
                "publisher": "Pub",
                "review_count": 5000,
            }

    monkeypatch.setattr(
        "salecast.clients.steam_client.rate_limited_appdetails_batch", fake_batch
    )
    survivors = discovery.enrich_and_filter_candidates(
        list(range(100)), min_age_months=6, target_count=3
    )
    assert len(survivors) == 3
    # only the candidates actually needed to hit the target should have been processed
    assert len(processed_ids) == 3


def test_enrich_and_filter_inserts_incrementally(monkeypatch):
    def fake_batch(app_ids, delay_sec=0):
        for app_id in app_ids:
            yield app_id, {
                "type": "game",
                "is_released": True,
                "release_date": "2020-01-01",
                "name": f"Game {app_id}",
                "genre": "RPG",
                "publisher": "Pub",
                "review_count": 5000,
            }

    monkeypatch.setattr(
        "salecast.clients.steam_client.rate_limited_appdetails_batch", fake_batch
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)

    survivors = discovery.enrich_and_filter_candidates([1, 2, 3], min_age_months=6, conn=conn)

    assert len(survivors) == 3
    assert conn.execute("SELECT COUNT(*) FROM tracked_games").fetchone()[0] == 3


def test_enrich_and_filter_prefers_steamspy_review_data(monkeypatch):
    def fake_batch(app_ids, delay_sec=0):
        for app_id in app_ids:
            yield app_id, {
                "type": "game",
                "is_released": True,
                "release_date": "2020-01-01",
                "name": "Popular Free Game",
                "genre": "Action",
                "publisher": "Pub",
                "review_count": 110,  # Steam's own (unreliable/low) count
            }

    monkeypatch.setattr(
        "salecast.clients.steam_client.rate_limited_appdetails_batch", fake_batch
    )
    survivors = discovery.enrich_and_filter_candidates(
        [42],
        min_age_months=6,
        review_data={42: {"review_count": 12000, "review_score_pct": 91.5}},
    )
    assert len(survivors) == 1
    assert survivors[0]["review_count"] == 12000
    assert survivors[0]["review_score_pct"] == 91.5


def test_insert_tracked_games_is_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)

    game = {
        "app_id": 1,
        "name": "Test Game",
        "genre": "Action",
        "publisher": "Pub",
        "release_date": "2020-01-01",
        "review_count": 1000,
        "review_score_pct": None,
        "first_tracked_date": "2026-07-12",
    }

    inserted_first = discovery.insert_tracked_games(conn, [game])
    inserted_second = discovery.insert_tracked_games(conn, [game])

    assert inserted_first == 1
    assert inserted_second == 0
    assert conn.execute("SELECT COUNT(*) FROM tracked_games").fetchone()[0] == 1

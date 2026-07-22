import sqlite3

import pytest
from fastapi.testclient import TestClient

from salecast import db
from salecast.api import app, get_connection


def _fixture_conn():
    # check_same_thread=False: FastAPI's TestClient runs the endpoint in a
    # worker thread, but this fixture creates one connection up front (in
    # the test's own thread) and reuses it across every simulated request -
    # safe here since tests run requests sequentially, not concurrently.
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)
    conn.execute(
        """
        INSERT INTO tracked_games
            (app_id, name, genre, publisher, release_date, review_count,
             review_score_pct, first_tracked_date)
        VALUES (730, 'Counter-Strike 2', 'Action', 'Valve', '2012-08-21', 500000, 88.0, '2026-01-01')
        """
    )
    conn.execute(
        "INSERT INTO price_history (app_id, date, price, discount_pct, source) "
        "VALUES (730, '2026-07-01', 4.99, 50, 'daily_scrape')"
    )
    conn.execute("INSERT INTO cluster_labels (app_id, cluster_id, last_updated) VALUES (730, 2, '2026-07-01')")
    conn.execute(
        "INSERT INTO smart_buy_scores (app_id, target_discount, horizon_days, probability, last_updated) "
        "VALUES (730, 50, 30, 0.75, '2026-07-01')"
    )
    conn.execute(
        "INSERT INTO deal_scores (app_id, composite_score, last_updated) VALUES (730, 82.5, '2026-07-01')"
    )
    conn.commit()
    return conn


@pytest.fixture
def conn():
    return _fixture_conn()


@pytest.fixture
def client(conn):
    def _override():
        yield conn

    app.dependency_overrides[get_connection] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_game_returns_full_profile(client):
    response = client.get("/game/730")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Counter-Strike 2"
    assert body["cluster_id"] == 2
    assert body["deal_score"] == 82.5
    assert body["current_discount_pct"] == 50
    assert body["smart_buy_probabilities"] == [
        {"target_discount": 50, "horizon_days": 30, "probability": 0.75}
    ]


def test_get_game_404_for_untracked_app(client):
    response = client.get("/game/999999999")

    assert response.status_code == 404


def test_get_game_handles_missing_derived_data(client, conn):
    # A game with no cluster/smart-buy/deal-score rows yet (e.g. just discovered)
    conn.execute(
        """
        INSERT INTO tracked_games
            (app_id, name, genre, publisher, release_date, review_count,
             review_score_pct, first_tracked_date)
        VALUES (999, 'Brand New Game', 'Indie', 'Indie Pub', '2026-07-01', 600, 80.0, '2026-07-20')
        """
    )
    conn.commit()

    response = client.get("/game/999")

    assert response.status_code == 200
    body = response.json()
    assert body["cluster_id"] is None
    assert body["deal_score"] is None
    assert body["current_discount_pct"] is None
    assert body["smart_buy_probabilities"] == []

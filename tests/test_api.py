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
        "INSERT INTO price_history (app_id, date, price, original_price, discount_pct, source) "
        "VALUES (730, '2026-07-01', 4.99, 9.99, 50, 'daily_scrape')"
    )
    conn.execute(
        """
        INSERT INTO cluster_labels
            (app_id, cluster_id, avg_discount_depth, discount_depth_std,
             discount_frequency_per_year, time_to_first_discount_days, discount_depth_trend, last_updated)
        VALUES (730, 2, 60.0, 10.0, 8.0, 100.0, 5.0, '2026-07-01')
        """
    )
    conn.execute(
        "INSERT INTO smart_buy_scores (app_id, target_discount, horizon_days, probability, last_updated) "
        "VALUES (730, 50, 30, 0.75, '2026-07-01')"
    )
    conn.execute(
        """
        INSERT INTO deal_scores
            (app_id, composite_score, discount_ratio, smart_buy_probability, review_confidence, last_updated)
        VALUES (730, 82.5, 0.9, 0.75, 0.95, '2026-07-01')
        """
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
    assert body["is_free"] is False
    assert body["cluster_id"] == 2
    assert body["deal_score"] == 82.5
    assert body["current_discount_pct"] == 50
    assert body["original_price"] == 9.99

    breakdown = {row["component"]: row["contribution"] for row in body["deal_score_breakdown"]}
    assert breakdown["discount_ratio"] == pytest.approx(36.0)
    assert breakdown["smart_buy_probability"] == pytest.approx(26.25, abs=0.1)
    assert breakdown["review_confidence"] == pytest.approx(23.75, abs=0.1)

    max_points = {row["component"]: row["max"] for row in body["deal_score_breakdown"]}
    assert max_points["discount_ratio"] == pytest.approx(40.0)
    assert max_points["smart_buy_probability"] == pytest.approx(35.0)
    assert max_points["review_confidence"] == pytest.approx(25.0)

    summary = body["discount_summary"]
    assert summary["historical_low_price"] == 4.99
    assert summary["historical_low_discount_pct"] == 50
    assert summary["avg_discount_depth"] == 60.0
    assert summary["discount_frequency_per_year"] == 8.0


def test_get_game_history_returns_price_series(client):
    response = client.get("/game/730/history")

    assert response.status_code == 200
    assert response.json() == [{"date": "2026-07-01", "price": 4.99, "discount_pct": 50}]


def test_get_game_history_404_for_untracked_app(client):
    response = client.get("/game/999999999/history")

    assert response.status_code == 404


def test_discount_summary_picks_the_deepest_historical_discount(client, conn):
    # A deeper, cheaper discount recorded on an earlier date should win over
    # today's smaller one - "historical low" means the best it's ever been,
    # not the most recent row.
    conn.execute(
        "INSERT INTO price_history (app_id, date, price, discount_pct, source) "
        "VALUES (730, '2025-11-29', 1.99, 80, 'itad_history')"
    )
    conn.commit()

    response = client.get("/game/730")

    summary = response.json()["discount_summary"]
    assert summary["historical_low_price"] == 1.99
    assert summary["historical_low_discount_pct"] == 80
    assert summary["historical_low_date"] == "2025-11-29"


def test_discount_summary_is_none_for_free_games(client, conn):
    conn.execute("UPDATE tracked_games SET is_free = 1 WHERE app_id = 730")
    conn.commit()

    response = client.get("/game/730")

    assert response.json()["discount_summary"] is None


def test_get_game_reports_is_free(client, conn):
    conn.execute(
        """
        INSERT INTO tracked_games
            (app_id, name, genre, publisher, release_date, review_count,
             review_score_pct, first_tracked_date, is_free)
        VALUES (440, 'Team Fortress 2', 'Action', 'Valve', '2007-10-10', 900000, 95.0, '2026-01-01', 1)
        """
    )
    conn.commit()

    response = client.get("/game/440")

    assert response.status_code == 200
    assert response.json()["is_free"] is True


def test_get_game_404_for_untracked_app(client):
    response = client.get("/game/999999999")

    assert response.status_code == 404


def test_search_returns_matches_ordered_by_review_count(client, conn):
    conn.execute(
        """
        INSERT INTO tracked_games
            (app_id, name, genre, publisher, release_date, review_count,
             review_score_pct, first_tracked_date)
        VALUES (10, 'Counter-Strike', 'Action', 'Valve', '2000-11-01', 100, 95.0, '2026-01-01')
        """
    )
    conn.commit()

    response = client.get("/search", params={"q": "counter"})

    assert response.status_code == 200
    names = [row["name"] for row in response.json()]
    assert names == ["Counter-Strike 2", "Counter-Strike"]  # 500000 reviews > 100


def test_search_is_case_insensitive(client):
    response = client.get("/search", params={"q": "COUNTER-strike"})

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_search_returns_empty_list_for_short_queries(client):
    response = client.get("/search", params={"q": "c"})

    assert response.status_code == 200
    assert response.json() == []


def test_search_returns_empty_list_for_no_matches(client):
    response = client.get("/search", params={"q": "nonexistent game xyz"})

    assert response.status_code == 200
    assert response.json() == []


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
    assert body["deal_score_breakdown"] is None
    assert body["discount_summary"] is None


def test_next_sale_estimate_is_none_while_game_is_on_sale(client):
    # fixture game 730 is currently 50% off
    assert client.get("/game/730").json()["next_sale_estimate"] is None


def test_next_sale_estimate_present_for_off_sale_game_with_history(client, conn):
    conn.execute(
        "INSERT INTO tracked_games (app_id, name, first_tracked_date) VALUES (500, 'Regular Seller', '2025-01-01')"
    )
    # eight 3-day sales roughly every 60 days, then back to full price
    for start, end in (
        ("2024-07-15", "2024-07-18"), ("2024-09-13", "2024-09-16"), ("2024-11-12", "2024-11-15"),
        ("2025-01-10", "2025-01-13"), ("2025-03-11", "2025-03-14"), ("2025-05-10", "2025-05-13"),
        ("2025-07-09", "2025-07-12"), ("2025-09-07", "2025-09-10"),
    ):
        conn.execute(
            "INSERT INTO price_history (app_id, date, price, discount_pct, source) VALUES (500, ?, 5.0, 50, 'itad_history')",
            (start,),
        )
        conn.execute(
            "INSERT INTO price_history (app_id, date, price, discount_pct, source) VALUES (500, ?, 10.0, 0, 'itad_history')",
            (end,),
        )
    conn.commit()

    estimate = client.get("/game/500").json()["next_sale_estimate"]

    assert estimate is not None
    assert estimate["past_sales"] == 8
    assert estimate["low_days"] <= estimate["high_days"]
    assert estimate["confidence"] in ("high", "medium", "low")


def test_next_sale_estimate_none_without_enough_history(client, conn):
    conn.execute("INSERT INTO tracked_games (app_id, name, first_tracked_date) VALUES (501, 'New', '2026-07-01')")
    conn.execute(
        "INSERT INTO price_history (app_id, date, price, discount_pct, source) VALUES (501, '2026-07-02', 10.0, 0, 'daily_scrape')"
    )
    conn.commit()

    assert client.get("/game/501").json()["next_sale_estimate"] is None

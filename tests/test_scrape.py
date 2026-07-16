import sqlite3

from salecast import db, scrape


def _make_conn_with_games(app_ids):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)
    for app_id in app_ids:
        conn.execute(
            """
            INSERT INTO tracked_games
                (app_id, name, genre, publisher, release_date, review_count,
                 review_score_pct, first_tracked_date)
            VALUES (?, 'Game', 'Action', 'Pub', '2020-01-01', 1000, 90.0, '2026-07-12')
            """,
            (app_id,),
        )
    conn.commit()
    return conn


def test_main_attempts_every_tracked_game(monkeypatch):
    conn = _make_conn_with_games([10, 20, 30])

    attempted_ids = []

    def fake_scrape_game(conn, app_id, **kwargs):
        attempted_ids.append(app_id)
        return 0

    monkeypatch.setattr(scrape, "scrape_game", fake_scrape_game)
    monkeypatch.setattr("time.sleep", lambda _: None)

    scrape.main(conn, delay_sec=0)

    assert attempted_ids == [10, 20, 30]


def test_main_respects_limit(monkeypatch):
    conn = _make_conn_with_games([1, 2, 3])

    attempted_ids = []

    def fake_scrape_game(conn, app_id, **kwargs):
        attempted_ids.append(app_id)
        return 1

    monkeypatch.setattr(scrape, "scrape_game", fake_scrape_game)
    monkeypatch.setattr("time.sleep", lambda _: None)

    scrape.main(conn, limit=2, delay_sec=0)

    assert attempted_ids == [1, 2]


def test_main_continues_after_a_game_raises(monkeypatch):
    conn = _make_conn_with_games([1, 2, 3])

    attempted_ids = []

    def fake_scrape_game(conn, app_id, **kwargs):
        attempted_ids.append(app_id)
        if app_id == 2:
            raise RuntimeError("boom")
        return 1

    monkeypatch.setattr(scrape, "scrape_game", fake_scrape_game)
    monkeypatch.setattr("time.sleep", lambda _: None)

    scrape.main(conn, delay_sec=0)

    assert attempted_ids == [1, 2, 3]


def test_scrape_game_inserts_price_row(monkeypatch):
    conn = _make_conn_with_games([730])

    monkeypatch.setattr(
        scrape.steam_client,
        "get_app_details",
        lambda app_id, session=None: {"price": 9.99, "discount_pct": 50},
    )

    inserted = scrape.scrape_game(conn, 730)

    assert inserted == 1
    row = conn.execute(
        "SELECT price, discount_pct, source FROM price_history WHERE app_id = 730"
    ).fetchone()
    assert row["price"] == 9.99
    assert row["discount_pct"] == 50
    assert row["source"] == "daily_scrape"


def test_scrape_game_skips_unpriced_apps(monkeypatch):
    conn = _make_conn_with_games([730])

    monkeypatch.setattr(
        scrape.steam_client, "get_app_details", lambda app_id, session=None: {"price": None}
    )

    inserted = scrape.scrape_game(conn, 730)

    assert inserted == 0
    count = conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
    assert count == 0

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
    monkeypatch.setattr(
        scrape.steamspy_client,
        "get_app_stats",
        lambda app_id, session=None: {"review_count": 100, "review_score_pct": 87.5},
    )
    monkeypatch.setattr("time.sleep", lambda _: None)

    inserted = scrape.scrape_game(conn, 730)

    assert inserted == 1
    row = conn.execute(
        "SELECT price, discount_pct, review_score_snapshot, source FROM price_history WHERE app_id = 730"
    ).fetchone()
    assert row["price"] == 9.99
    assert row["discount_pct"] == 50
    assert row["review_score_snapshot"] == 87.5
    assert row["source"] == "daily_scrape"


def test_scrape_game_stores_original_price(monkeypatch):
    conn = _make_conn_with_games([730])

    monkeypatch.setattr(
        scrape.steam_client,
        "get_app_details",
        lambda app_id, session=None: {"price": 9.99, "original_price": 19.99, "discount_pct": 50},
    )
    monkeypatch.setattr(scrape.steamspy_client, "get_app_stats", lambda app_id, session=None: None)
    monkeypatch.setattr("time.sleep", lambda _: None)

    scrape.scrape_game(conn, 730)

    row = conn.execute("SELECT original_price FROM price_history WHERE app_id = 730").fetchone()
    assert row["original_price"] == 19.99


def test_scrape_game_stores_null_review_score_when_steamspy_has_no_data(monkeypatch):
    conn = _make_conn_with_games([730])

    monkeypatch.setattr(
        scrape.steam_client,
        "get_app_details",
        lambda app_id, session=None: {"price": 9.99, "discount_pct": 50},
    )
    monkeypatch.setattr(scrape.steamspy_client, "get_app_stats", lambda app_id, session=None: None)
    monkeypatch.setattr("time.sleep", lambda _: None)

    inserted = scrape.scrape_game(conn, 730)

    assert inserted == 1
    row = conn.execute(
        "SELECT review_score_snapshot FROM price_history WHERE app_id = 730"
    ).fetchone()
    assert row["review_score_snapshot"] is None


def test_scrape_game_skips_unpriced_apps(monkeypatch):
    conn = _make_conn_with_games([730])

    monkeypatch.setattr(
        scrape.steam_client, "get_app_details", lambda app_id, session=None: {"price": None}
    )
    monkeypatch.setattr("time.sleep", lambda _: None)

    inserted = scrape.scrape_game(conn, 730)

    assert inserted == 0
    count = conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
    assert count == 0


def test_scrape_game_skips_non_usd_price(monkeypatch):
    conn = _make_conn_with_games([730])

    monkeypatch.setattr(
        scrape.steam_client,
        "get_app_details",
        lambda app_id, session=None: {"price": 1349.7, "discount_pct": 75, "currency": "INR"},
    )
    monkeypatch.setattr("time.sleep", lambda _: None)

    inserted = scrape.scrape_game(conn, 730)

    assert inserted == 0
    count = conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
    assert count == 0


def test_scrape_game_marks_is_free_when_no_price_even_if_steam_says_not_free(monkeypatch):
    # Steam's is_free flag doesn't reliably update for games that converted
    # to free-to-play after launch (e.g. Rocket League) - price_overview is
    # permanently absent but is_free still reports False. A missing price
    # should be treated as free regardless of that flag, or the game's last
    # historical price sits there forever looking current.
    conn = _make_conn_with_games([730])

    monkeypatch.setattr(
        scrape.steam_client,
        "get_app_details",
        lambda app_id, session=None: {"price": None, "is_free": False},
    )
    monkeypatch.setattr("time.sleep", lambda _: None)

    inserted = scrape.scrape_game(conn, 730)

    assert inserted == 0
    row = conn.execute("SELECT is_free FROM tracked_games WHERE app_id = 730").fetchone()
    assert row["is_free"] == 1


def test_scrape_game_returns_zero_when_request_fails(monkeypatch):
    conn = _make_conn_with_games([730])

    monkeypatch.setattr(scrape.steam_client, "get_app_details", lambda app_id, session=None: None)
    monkeypatch.setattr("time.sleep", lambda _: None)

    assert scrape.scrape_game(conn, 730) == 0


def test_scrape_game_marks_is_free_and_skips_price_row(monkeypatch):
    conn = _make_conn_with_games([730])

    monkeypatch.setattr(
        scrape.steam_client,
        "get_app_details",
        lambda app_id, session=None: {"price": None, "is_free": True},
    )
    monkeypatch.setattr("time.sleep", lambda _: None)

    inserted = scrape.scrape_game(conn, 730)

    assert inserted == 0
    row = conn.execute("SELECT is_free FROM tracked_games WHERE app_id = 730").fetchone()
    assert row["is_free"] == 1


def test_scrape_game_keeps_is_free_false_for_paid_games(monkeypatch):
    conn = _make_conn_with_games([730])

    monkeypatch.setattr(
        scrape.steam_client,
        "get_app_details",
        lambda app_id, session=None: {"price": 9.99, "discount_pct": 0, "is_free": False},
    )
    monkeypatch.setattr(scrape.steamspy_client, "get_app_stats", lambda app_id, session=None: None)
    monkeypatch.setattr("time.sleep", lambda _: None)

    scrape.scrape_game(conn, 730)

    row = conn.execute("SELECT is_free FROM tracked_games WHERE app_id = 730").fetchone()
    assert row["is_free"] == 0


def test_scrape_game_clears_derived_scores_when_newly_free(monkeypatch):
    conn = _make_conn_with_games([730])
    conn.execute("INSERT INTO cluster_labels (app_id, cluster_id, last_updated) VALUES (730, 2, 'x')")
    conn.execute(
        "INSERT INTO smart_buy_scores (app_id, target_discount, horizon_days, probability, last_updated) "
        "VALUES (730, 50, 30, 0.8, 'x')"
    )
    conn.execute("INSERT INTO deal_scores (app_id, composite_score, last_updated) VALUES (730, 90.0, 'x')")
    conn.commit()

    monkeypatch.setattr(
        scrape.steam_client,
        "get_app_details",
        lambda app_id, session=None: {"price": None, "is_free": True},
    )
    monkeypatch.setattr("time.sleep", lambda _: None)

    scrape.scrape_game(conn, 730)

    assert conn.execute("SELECT COUNT(*) FROM cluster_labels WHERE app_id = 730").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM smart_buy_scores WHERE app_id = 730").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM deal_scores WHERE app_id = 730").fetchone()[0] == 0

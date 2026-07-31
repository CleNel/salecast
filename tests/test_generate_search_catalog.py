import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from salecast import db
from generate_search_catalog import build_catalog


def _make_conn():
    conn = db.get_connection(":memory:")
    db.init_schema(conn)
    return conn


def _add_game(conn, app_id, name, is_free=0, genre=None, publisher=None, release_date=None,
              review_count=None, review_score_pct=None):
    conn.execute(
        "INSERT INTO tracked_games "
        "(app_id, name, genre, publisher, release_date, review_count, review_score_pct, "
        "first_tracked_date, is_free) VALUES (?, ?, ?, ?, ?, ?, ?, '2026-01-01', ?)",
        (app_id, name, genre, publisher, release_date, review_count, review_score_pct, is_free),
    )


def _add_price(conn, app_id, date, price, discount_pct, original_price=None):
    conn.execute(
        "INSERT INTO price_history (app_id, date, price, original_price, discount_pct, source) "
        "VALUES (?, ?, ?, ?, ?, 'daily_scrape')",
        (app_id, date, price, original_price, discount_pct),
    )


def _add_deal_score(conn, app_id, composite_score):
    conn.execute(
        "INSERT INTO deal_scores (app_id, composite_score, last_updated) VALUES (?, ?, 'x')",
        (app_id, composite_score),
    )


def test_excludes_free_games():
    conn = _make_conn()
    _add_game(conn, 1, "Free Game", is_free=1)
    _add_price(conn, 1, "2026-07-23", 0, 100)
    conn.commit()

    catalog = build_catalog(conn)

    assert catalog["games"] == []


def test_includes_genre_publisher_and_release_year():
    conn = _make_conn()
    _add_game(conn, 2, "Some RPG", genre="RPG", publisher="Acme", release_date="2019-05-01")
    _add_price(conn, 2, "2026-07-23", 19.99, 0, original_price=19.99)
    conn.commit()

    catalog = build_catalog(conn)

    game = catalog["games"][0]
    assert game["genre"] == "RPG"
    assert game["publisher"] == "Acme"
    assert game["release_year"] == 2019


def test_uses_latest_price_row_not_earliest():
    conn = _make_conn()
    _add_game(conn, 3, "Price Changed")
    _add_price(conn, 3, "2026-07-01", 59.99, 0)
    _add_price(conn, 3, "2026-07-23", 14.99, 75, original_price=59.99)
    conn.commit()

    catalog = build_catalog(conn)

    game = catalog["games"][0]
    assert game["price"] == 14.99
    assert game["discount_pct"] == 75
    assert game["original_price"] == 59.99


def test_game_without_price_history_still_appears_with_null_price():
    conn = _make_conn()
    _add_game(conn, 4, "Just Discovered")
    conn.commit()

    catalog = build_catalog(conn)

    game = catalog["games"][0]
    assert game["price"] is None
    assert game["discount_pct"] == 0


def test_game_without_deal_score_has_null_deal_score():
    conn = _make_conn()
    _add_game(conn, 5, "Not Scored Yet")
    _add_price(conn, 5, "2026-07-23", 9.99, 0)
    conn.commit()

    catalog = build_catalog(conn)

    assert catalog["games"][0]["deal_score"] is None


def test_includes_deal_score_when_present():
    conn = _make_conn()
    _add_game(conn, 6, "Scored")
    _add_price(conn, 6, "2026-07-23", 9.99, 50)
    _add_deal_score(conn, 6, 72.345)
    conn.commit()

    catalog = build_catalog(conn)

    assert catalog["games"][0]["deal_score"] == 72.3

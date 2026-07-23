import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from salecast import db
from generate_sidebar_deals import build_snapshot


def _make_conn():
    conn = db.get_connection(":memory:")
    db.init_schema(conn)
    return conn


def _add_game(conn, app_id, name, is_free=0):
    conn.execute(
        "INSERT INTO tracked_games (app_id, name, first_tracked_date, is_free) VALUES (?, ?, '2026-01-01', ?)",
        (app_id, name, is_free),
    )


def _add_price(conn, app_id, date, price, discount_pct):
    conn.execute(
        "INSERT INTO price_history (app_id, date, price, discount_pct, source) VALUES (?, ?, ?, ?, 'daily_scrape')",
        (app_id, date, price, discount_pct),
    )


def _add_deal_score(conn, app_id, composite_score):
    conn.execute(
        "INSERT INTO deal_scores (app_id, composite_score, last_updated) VALUES (?, ?, 'x')",
        (app_id, composite_score),
    )


def test_top_deals_ranks_by_composite_score_and_requires_active_discount():
    conn = _make_conn()
    _add_game(conn, 1, "High Score No Discount")
    _add_price(conn, 1, "2026-07-23", 59.99, 0)
    _add_deal_score(conn, 1, 95.0)

    _add_game(conn, 2, "Mid Score Discounted")
    _add_price(conn, 2, "2026-07-23", 14.99, 75)
    _add_deal_score(conn, 2, 80.0)

    conn.commit()

    snapshot = build_snapshot(conn, limit=5)

    # Game 1 has the higher stored deal_score but isn't currently on sale,
    # so it must not show up in a "deal" list at all.
    top_ids = [g["app_id"] for g in snapshot["top_deals"]]
    assert top_ids == [2]


def test_top_deals_excludes_free_games():
    conn = _make_conn()
    _add_game(conn, 3, "Free Game", is_free=1)
    _add_price(conn, 3, "2026-07-23", 0, 100)
    _add_deal_score(conn, 3, 90.0)
    conn.commit()

    snapshot = build_snapshot(conn, limit=5)

    assert snapshot["top_deals"] == []


def test_new_deals_detects_discount_that_just_started():
    conn = _make_conn()
    _add_game(conn, 10, "Freshly Discounted")
    _add_price(conn, 10, "2026-07-22", 59.99, 0)
    _add_price(conn, 10, "2026-07-23", 14.99, 75)

    _add_game(conn, 11, "Been On Sale A While")
    _add_price(conn, 11, "2026-07-22", 9.99, 50)
    _add_price(conn, 11, "2026-07-23", 9.99, 50)
    conn.commit()

    snapshot = build_snapshot(conn, limit=5)

    new_ids = [g["app_id"] for g in snapshot["new_deals"]]
    assert new_ids == [10]


def test_new_deals_works_without_a_deal_score_row():
    conn = _make_conn()
    _add_game(conn, 20, "Not Yet Scored")
    _add_price(conn, 20, "2026-07-22", 19.99, 0)
    _add_price(conn, 20, "2026-07-23", 9.99, 50)
    conn.commit()

    snapshot = build_snapshot(conn, limit=5)

    assert snapshot["new_deals"][0]["app_id"] == 20
    assert snapshot["new_deals"][0]["deal_score"] is None


def test_respects_limit():
    conn = _make_conn()
    for i in range(3):
        app_id = 100 + i
        _add_game(conn, app_id, f"Game {i}")
        _add_price(conn, app_id, "2026-07-23", 9.99, 50)
        _add_deal_score(conn, app_id, 70.0 + i)
    conn.commit()

    snapshot = build_snapshot(conn, limit=2)

    assert len(snapshot["top_deals"]) == 2

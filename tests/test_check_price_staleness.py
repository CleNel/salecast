import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from salecast import db
from check_price_staleness import find_stale_games


def _make_conn():
    conn = db.get_connection(":memory:")
    db.init_schema(conn)
    return conn


def _add_game(conn, app_id, name, is_free=0):
    conn.execute(
        "INSERT INTO tracked_games (app_id, name, first_tracked_date, is_free) VALUES (?, ?, '2020-01-01', ?)",
        (app_id, name, is_free),
    )


def _add_price(conn, app_id, date_str):
    conn.execute(
        "INSERT INTO price_history (app_id, date, price, discount_pct, source) VALUES (?, ?, 9.99, 0, 'daily_scrape')",
        (app_id, date_str),
    )


def test_flags_game_with_old_price_data():
    conn = _make_conn()
    _add_game(conn, 1, "Stale Game")
    _add_price(conn, 1, "2020-01-01")
    conn.commit()

    stale = find_stale_games(conn, max_age_days=14, today=date(2026, 7, 23))

    assert [g["app_id"] for g in stale] == [1]


def test_flags_game_with_no_price_history_at_all():
    conn = _make_conn()
    _add_game(conn, 2, "Never Scraped")
    conn.commit()

    stale = find_stale_games(conn, max_age_days=14, today=date(2026, 7, 23))

    assert [g["app_id"] for g in stale] == [2]


def test_does_not_flag_game_with_recent_price():
    conn = _make_conn()
    _add_game(conn, 3, "Fresh Game")
    _add_price(conn, 3, "2026-07-22")
    conn.commit()

    stale = find_stale_games(conn, max_age_days=14, today=date(2026, 7, 23))

    assert stale == []


def test_does_not_flag_free_games_regardless_of_price_age():
    conn = _make_conn()
    _add_game(conn, 4, "Free Game", is_free=1)
    conn.commit()

    stale = find_stale_games(conn, max_age_days=14, today=date(2026, 7, 23))

    assert stale == []

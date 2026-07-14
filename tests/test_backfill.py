import sqlite3

from salecast import backfill, db


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


def test_main_skips_already_backfilled_games(monkeypatch):
    conn = _make_conn_with_games([1, 2, 3])
    conn.execute(
        "INSERT INTO price_history (app_id, date, price, source) VALUES (1, '2026-07-12', 9.99, 'itad_backfill')"
    )
    conn.commit()

    attempted_ids = []

    def fake_backfill_game(conn, app_id, **kwargs):
        attempted_ids.append(app_id)
        return 0

    monkeypatch.setattr(backfill, "backfill_game", fake_backfill_game)
    monkeypatch.setattr("time.sleep", lambda _: None)

    backfill.main(conn, delay_sec=0)

    assert attempted_ids == [2, 3]


def test_main_attempts_all_games_when_none_backfilled_yet(monkeypatch):
    conn = _make_conn_with_games([10, 20])

    attempted_ids = []

    def fake_backfill_game(conn, app_id, **kwargs):
        attempted_ids.append(app_id)
        return 0

    monkeypatch.setattr(backfill, "backfill_game", fake_backfill_game)
    monkeypatch.setattr("time.sleep", lambda _: None)

    backfill.main(conn, delay_sec=0)

    assert attempted_ids == [10, 20]

import sqlite3

from salecast import backfill, db


def _make_conn_with_games(games):
    """games: list of (app_id, release_date) or plain app_ids (release_date defaults)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)
    for game in games:
        app_id, release_date = game if isinstance(game, tuple) else (game, "2020-01-01")
        conn.execute(
            """
            INSERT INTO tracked_games
                (app_id, name, genre, publisher, release_date, review_count,
                 review_score_pct, first_tracked_date)
            VALUES (?, 'Game', 'Action', 'Pub', ?, 1000, 90.0, '2026-07-12')
            """,
            (app_id, release_date),
        )
    conn.commit()
    return conn


def test_main_skips_already_backfilled_games(monkeypatch):
    conn = _make_conn_with_games([1, 2, 3])
    conn.execute(
        "INSERT INTO price_history (app_id, date, price, source) VALUES (1, '2026-07-12', 9.99, 'itad_history')"
    )
    conn.commit()

    attempted_ids = []

    def fake_backfill_game(conn, app_id, release_date, **kwargs):
        attempted_ids.append(app_id)
        return 0

    monkeypatch.setattr(backfill, "backfill_game", fake_backfill_game)
    monkeypatch.setattr("time.sleep", lambda _: None)

    backfill.main(conn, delay_sec=0)

    assert attempted_ids == [2, 3]


def test_main_attempts_all_games_when_none_backfilled_yet(monkeypatch):
    conn = _make_conn_with_games([10, 20])

    attempted_ids = []

    def fake_backfill_game(conn, app_id, release_date, **kwargs):
        attempted_ids.append(app_id)
        return 0

    monkeypatch.setattr(backfill, "backfill_game", fake_backfill_game)
    monkeypatch.setattr("time.sleep", lambda _: None)

    backfill.main(conn, delay_sec=0)

    assert attempted_ids == [10, 20]


def test_main_passes_release_date_through(monkeypatch):
    conn = _make_conn_with_games([(1, "2015-06-01")])

    seen_release_dates = []

    def fake_backfill_game(conn, app_id, release_date, **kwargs):
        seen_release_dates.append(release_date)
        return 0

    monkeypatch.setattr(backfill, "backfill_game", fake_backfill_game)
    monkeypatch.setattr("time.sleep", lambda _: None)

    backfill.main(conn, delay_sec=0)

    assert seen_release_dates == ["2015-06-01"]


def test_backfill_game_inserts_one_row_per_event(monkeypatch):
    conn = _make_conn_with_games([(42, "2015-01-01")])

    monkeypatch.setattr(backfill.itad_client, "resolve_itad_id", lambda app_id: "itad-id-42")
    monkeypatch.setattr(
        backfill.itad_client,
        "get_price_history",
        lambda itad_id, since=None, region="US": [
            {"date": "2026-06-18", "price": 3.99, "discount_pct": 90},
            {"date": "2020-01-01", "price": 39.99, "discount_pct": 0},
        ],
    )
    monkeypatch.setattr("time.sleep", lambda _: None)

    inserted = backfill.backfill_game(conn, 42, "2015-01-01")

    assert inserted == 2
    rows = conn.execute(
        "SELECT date, price, discount_pct, source FROM price_history WHERE app_id = 42 ORDER BY date"
    ).fetchall()
    assert [dict(r) for r in rows] == [
        {"date": "2020-01-01", "price": 39.99, "discount_pct": 0, "source": "itad_history"},
        {"date": "2026-06-18", "price": 3.99, "discount_pct": 90, "source": "itad_history"},
    ]


def test_backfill_game_returns_zero_when_no_itad_match(monkeypatch):
    conn = _make_conn_with_games([42])

    monkeypatch.setattr(backfill.itad_client, "resolve_itad_id", lambda app_id: None)
    monkeypatch.setattr("time.sleep", lambda _: None)

    inserted = backfill.backfill_game(conn, 42, "2015-01-01")

    assert inserted == 0
    assert conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0] == 0


def test_backfill_game_uses_execute_batch_when_available(monkeypatch):
    class _FakeD1Conn:
        def __init__(self):
            self.batches = []

        def execute_batch(self, statements):
            self.batches.append(statements)
            return len(statements)

    conn = _FakeD1Conn()

    monkeypatch.setattr(backfill.itad_client, "resolve_itad_id", lambda app_id: "itad-id-42")
    monkeypatch.setattr(
        backfill.itad_client,
        "get_price_history",
        lambda itad_id, since=None, region="US": [
            {"date": "2026-06-18", "price": 3.99, "discount_pct": 90},
            {"date": "2020-01-01", "price": 39.99, "discount_pct": 0},
        ],
    )
    monkeypatch.setattr("time.sleep", lambda _: None)

    inserted = backfill.backfill_game(conn, 42, "2015-01-01")

    assert inserted == 2
    assert len(conn.batches) == 1
    assert len(conn.batches[0]) == 2


def test_backfill_game_returns_zero_when_no_history(monkeypatch):
    conn = _make_conn_with_games([42])

    monkeypatch.setattr(backfill.itad_client, "resolve_itad_id", lambda app_id: "itad-id-42")
    monkeypatch.setattr(
        backfill.itad_client, "get_price_history", lambda itad_id, since=None, region="US": []
    )
    monkeypatch.setattr("time.sleep", lambda _: None)

    inserted = backfill.backfill_game(conn, 42, "2015-01-01")

    assert inserted == 0

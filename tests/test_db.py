import sqlite3

from salecast import db


def test_init_schema_creates_tables_on_sqlite_connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    db.init_schema(conn)

    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {"tracked_games", "price_history", "cluster_labels", "smart_buy_scores", "deal_scores"} <= tables


def test_init_schema_works_without_executescript_support():
    """D1Connection has no executescript() (only sqlite3.Connection does) -
    init_schema must fall back to executing schema.sql one statement at a
    time for any connection lacking it."""

    class _FakeD1Conn:
        def __init__(self):
            self.executed = []

        def execute(self, sql):
            self.executed.append(sql)

    conn = _FakeD1Conn()

    db.init_schema(conn)

    assert len(conn.executed) >= 5
    assert any("CREATE TABLE" in s and "smart_buy_scores" in s for s in conn.executed)

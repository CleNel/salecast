import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"


def get_connection(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn) -> None:
    """Applies sql/schema.sql (all CREATE TABLE/INDEX IF NOT EXISTS - a
    no-op for tables that already exist with a different shape, so this is
    safe to call unconditionally). Works for both sqlite3.Connection and
    D1Connection, which has no executescript() and must run one statement
    per HTTP call."""
    schema_sql = SCHEMA_PATH.read_text()
    if hasattr(conn, "executescript"):
        conn.executescript(schema_sql)
        conn.commit()
    else:
        for statement in schema_sql.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(statement)

    _add_column_if_missing(conn, "tracked_games", "is_free", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "price_history", "original_price", "REAL")
    for column in (
        "avg_discount_depth", "discount_depth_std", "discount_frequency_per_year",
        "time_to_first_discount_days", "discount_depth_trend",
    ):
        _add_column_if_missing(conn, "cluster_labels", column, "REAL")
    for column in ("discount_ratio", "smart_buy_probability", "review_confidence"):
        _add_column_if_missing(conn, "deal_scores", column, "REAL")


def _add_column_if_missing(conn, table: str, column: str, ddl: str) -> None:
    """CREATE TABLE IF NOT EXISTS can't add a column to a table that
    already exists from before that column was introduced (local sqlite
    files created earlier, or the live D1 database) - ALTER TABLE ADD
    COLUMN is the only way, and it errors if the column is already there,
    so this makes it idempotent to call on every init_schema()."""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    except Exception as exc:
        if "duplicate column" not in str(exc).lower():
            raise

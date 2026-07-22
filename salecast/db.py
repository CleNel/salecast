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
        return

    for statement in schema_sql.split(";"):
        statement = statement.strip()
        if statement:
            conn.execute(statement)

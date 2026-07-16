import logging
import sqlite3
import time

from salecast import config
from salecast.clients import itad_client

logger = logging.getLogger(__name__)


def backfill_game(
    conn: sqlite3.Connection,
    app_id: int,
    release_date: str | None,
    region: str = "US",
    intra_call_delay_sec: float = config.ITAD_INTRA_CALL_DELAY_SEC,
) -> int:
    """Resolves app_id's ITAD id, fetches its full Steam price history back
    to release_date, and inserts one price_history row per historical
    price/discount change (source='itad_history'). Returns rows inserted
    (0 if no ITAD match or no history on record).

    Sleeps intra_call_delay_sec between the two ITAD calls this makes
    (id resolution, then history lookup) so a single game's backfill doesn't
    burst two requests back-to-back against ITAD's rate limit."""
    itad_id = itad_client.resolve_itad_id(app_id)
    if itad_id is None:
        return 0

    time.sleep(intra_call_delay_sec)

    since = f"{release_date}T00:00:00Z" if release_date else None
    events = itad_client.get_price_history(itad_id, since=since, region=region)
    if not events:
        return 0

    inserted = 0
    for event in events:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO price_history (app_id, date, price, discount_pct, source)
            VALUES (?, ?, ?, ?, 'itad_history')
            """,
            (app_id, event["date"], event["price"], event["discount_pct"]),
        )
        inserted += cursor.rowcount
    conn.commit()
    return inserted


def _already_backfilled_app_ids(conn: sqlite3.Connection) -> set[int]:
    rows = conn.execute(
        "SELECT DISTINCT app_id FROM price_history WHERE source = 'itad_history'"
    ).fetchall()
    return {row[0] for row in rows}


def main(conn: sqlite3.Connection, limit: int | None = None, delay_sec: float = config.ITAD_DELAY_SEC) -> None:
    rows = conn.execute("SELECT app_id, release_date FROM tracked_games ORDER BY app_id").fetchall()
    all_games = [(row["app_id"], row["release_date"]) for row in rows]

    skip_ids = _already_backfilled_app_ids(conn)
    games = [(app_id, release_date) for app_id, release_date in all_games if app_id not in skip_ids]
    logger.info(
        "Skipping %d already-backfilled games; %d remaining to attempt",
        len(all_games) - len(games), len(games),
    )

    if limit is not None:
        games = games[:limit]

    attempted = 0
    matched = 0
    rows_inserted = 0

    for app_id, release_date in games:
        attempted += 1
        try:
            inserted = backfill_game(conn, app_id, release_date)
        except itad_client.MissingApiKeyError:
            raise
        except Exception:
            logger.exception("Backfill failed for app_id=%d, continuing", app_id)
            inserted = 0

        if inserted:
            matched += 1
            rows_inserted += inserted

        if attempted % 50 == 0:
            logger.info("Backfill progress: %d/%d games processed", attempted, len(games))

        time.sleep(delay_sec)

    logger.info(
        "Backfill complete: %d attempted, %d matched, %d rows inserted, %d unmatched",
        attempted, matched, rows_inserted, attempted - matched,
    )

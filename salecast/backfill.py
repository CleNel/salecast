import logging
import sqlite3
import time
from datetime import date

from salecast import config
from salecast.clients import itad_client

logger = logging.getLogger(__name__)


def backfill_game(
    conn: sqlite3.Connection,
    app_id: int,
    region: str = "US",
    intra_call_delay_sec: float = config.ITAD_INTRA_CALL_DELAY_SEC,
) -> int:
    """Resolves app_id's ITAD id, fetches its historical low, and inserts a
    row into price_history (source='itad_backfill'). Returns rows inserted
    (0 if no ITAD match or no historical low on record).

    Sleeps intra_call_delay_sec between the two ITAD calls this makes
    (id resolution, then price lookup) so a single game's backfill doesn't
    burst two requests back-to-back against ITAD's rate limit."""
    itad_id = itad_client.resolve_itad_id(app_id)
    if itad_id is None:
        return 0

    time.sleep(intra_call_delay_sec)

    low = itad_client.get_historical_low(itad_id, region=region)
    if low is None or low.get("price") is None:
        return 0

    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO price_history (app_id, date, price, discount_pct, source)
        VALUES (?, ?, ?, NULL, 'itad_backfill')
        """,
        (app_id, date.today().isoformat(), low["price"]),
    )
    conn.commit()
    return cursor.rowcount


def _already_backfilled_app_ids(conn: sqlite3.Connection) -> set[int]:
    rows = conn.execute(
        "SELECT DISTINCT app_id FROM price_history WHERE source = 'itad_backfill'"
    ).fetchall()
    return {row[0] for row in rows}


def main(conn: sqlite3.Connection, limit: int | None = None, delay_sec: float = config.ITAD_DELAY_SEC) -> None:
    rows = conn.execute("SELECT app_id FROM tracked_games ORDER BY app_id").fetchall()
    all_app_ids = [row["app_id"] for row in rows]

    skip_ids = _already_backfilled_app_ids(conn)
    app_ids = [app_id for app_id in all_app_ids if app_id not in skip_ids]
    logger.info(
        "Skipping %d already-backfilled games; %d remaining to attempt",
        len(all_app_ids) - len(app_ids), len(app_ids),
    )

    if limit is not None:
        app_ids = app_ids[:limit]

    attempted = 0
    matched = 0
    rows_inserted = 0

    for app_id in app_ids:
        attempted += 1
        try:
            inserted = backfill_game(conn, app_id)
        except itad_client.MissingApiKeyError:
            raise
        except Exception:
            logger.exception("Backfill failed for app_id=%d, continuing", app_id)
            inserted = 0

        if inserted:
            matched += 1
            rows_inserted += inserted

        if attempted % 50 == 0:
            logger.info("Backfill progress: %d/%d games processed", attempted, len(app_ids))

        time.sleep(delay_sec)

    logger.info(
        "Backfill complete: %d attempted, %d matched, %d rows inserted, %d unmatched",
        attempted, matched, rows_inserted, attempted - matched,
    )

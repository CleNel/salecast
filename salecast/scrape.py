import logging
import sqlite3
import time
from datetime import date

import requests

from salecast import config
from salecast.clients import steam_client, steamspy_client

logger = logging.getLogger(__name__)


def scrape_game(
    conn: sqlite3.Connection,
    app_id: int,
    session: requests.Session | None = None,
    intra_call_delay_sec: float = config.SCRAPE_INTRA_CALL_DELAY_SEC,
) -> int:
    """Fetches app_id's current price/discount from Steam's appdetails, plus
    a review-score snapshot from SteamSpy, and inserts a row into
    price_history (source='daily_scrape'). Returns rows inserted (0 if the
    app has no store listing or isn't currently priced, e.g. free-to-play).

    Sleeps intra_call_delay_sec between the two calls this makes (Steam
    appdetails, then SteamSpy) so a single game's scrape doesn't burst both
    APIs back-to-back."""
    details = steam_client.get_app_details(app_id, session=session)
    if details is None or details.get("price") is None:
        return 0

    time.sleep(intra_call_delay_sec)
    stats = steamspy_client.get_app_stats(app_id, session=session)
    review_score_snapshot = stats["review_score_pct"] if stats else None

    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO price_history
            (app_id, date, price, discount_pct, review_score_snapshot, source)
        VALUES (?, ?, ?, ?, ?, 'daily_scrape')
        """,
        (
            app_id,
            date.today().isoformat(),
            details["price"],
            details.get("discount_pct"),
            review_score_snapshot,
        ),
    )
    conn.commit()
    return cursor.rowcount


def main(
    conn: sqlite3.Connection,
    limit: int | None = None,
    delay_sec: float = config.STEAM_APPDETAILS_DELAY_SEC,
) -> None:
    rows = conn.execute("SELECT app_id FROM tracked_games ORDER BY app_id").fetchall()
    app_ids = [row["app_id"] for row in rows]

    if limit is not None:
        app_ids = app_ids[:limit]

    session = requests.Session()
    attempted = 0
    recorded = 0

    for app_id in app_ids:
        attempted += 1
        try:
            inserted = scrape_game(conn, app_id, session=session)
        except Exception:
            logger.exception("Scrape failed for app_id=%d, continuing", app_id)
            inserted = 0

        recorded += inserted

        if attempted % 50 == 0:
            logger.info("Daily scrape progress: %d/%d games processed", attempted, len(app_ids))

        time.sleep(delay_sec)

    logger.info(
        "Daily scrape complete: %d attempted, %d price rows recorded, %d skipped/failed",
        attempted, recorded, attempted - recorded,
    )

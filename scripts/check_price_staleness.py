#!/usr/bin/env python
"""Flags tracked (non-free) games with no price_history row in the last N
days. The daily scrape should touch every tracked game every day, so a game
going quiet usually means something's actually wrong (a persistent fetch
failure, an is_free-detection gap, etc.) rather than a coincidence - this is
exactly how ARK: Survival Evolved sat showing a 2022 price as "current" for
months without anyone noticing. Exits non-zero so this can run as a weekly
CI step and surface as a failed run instead of rotting silently."""
import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from salecast import config, db  # noqa: E402
from salecast.clients.d1_client import D1Connection  # noqa: E402

logger = logging.getLogger(__name__)

STALE_SQL = """
    SELECT tg.app_id, tg.name, MAX(ph.date) AS latest_date
    FROM tracked_games tg
    LEFT JOIN price_history ph ON ph.app_id = tg.app_id
    WHERE tg.is_free = 0
    GROUP BY tg.app_id, tg.name
    HAVING latest_date IS NULL OR latest_date < ?
"""


def find_stale_games(conn, max_age_days: int, today: date | None = None) -> list[dict]:
    today = today or date.today()
    cutoff = (today - timedelta(days=max_age_days)).isoformat()
    rows = conn.execute(STALE_SQL, (cutoff,)).fetchall()
    return [{"app_id": row["app_id"], "name": row["name"], "latest_date": row["latest_date"]} for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Flag tracked (non-free) games with no recent price data")
    parser.add_argument("--target", choices=["sqlite", "d1"], default="sqlite")
    parser.add_argument("--db-path", type=str, default=config.DB_PATH)
    parser.add_argument(
        "--max-age-days", type=int, default=14,
        help="Flag games with no price_history row within this many days",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    conn = D1Connection() if args.target == "d1" else db.get_connection(args.db_path)
    db.init_schema(conn)

    stale = find_stale_games(conn, args.max_age_days)

    if not stale:
        print(f"No stale games found (every tracked, non-free game has price data within {args.max_age_days} days)")
        return

    print(f"{len(stale)} tracked games have no price data within {args.max_age_days} days:")
    for game in stale:
        print(f"  app_id={game['app_id']:<10} last_seen={game['latest_date'] or 'never':<12} {game['name']}")

    sys.exit(1)


if __name__ == "__main__":
    main()

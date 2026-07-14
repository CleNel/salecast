#!/usr/bin/env python
import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from salecast import config, db, discovery  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover qualifying Steam games")
    parser.add_argument("--min-reviews", type=int, default=config.MIN_REVIEWS)
    parser.add_argument("--min-age-months", type=int, default=config.MIN_AGE_MONTHS)
    parser.add_argument("--target-count", type=int, default=config.TARGET_TRACKED_COUNT)
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap the SteamSpy candidate set for a quick smoke test",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    conn = db.get_connection(config.DB_PATH)
    db.init_schema(conn)

    start = time.time()
    discovery.main(
        conn,
        min_reviews=args.min_reviews,
        min_age_months=args.min_age_months,
        target_count=args.target_count,
        limit=args.limit,
    )
    elapsed = time.time() - start

    count = conn.execute("SELECT COUNT(*) FROM tracked_games").fetchone()[0]
    print(f"tracked_games now has {count} rows (elapsed {elapsed:.1f}s)")


if __name__ == "__main__":
    main()

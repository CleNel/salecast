#!/usr/bin/env python
import argparse
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from salecast import config, db, scrape  # noqa: E402
from salecast.clients.d1_client import D1Connection  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape current Steam prices for tracked games")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only scrape the first N tracked games (smoke test)",
    )
    parser.add_argument(
        "--target", choices=["sqlite", "d1"], default="sqlite",
        help="Storage backend: local SQLite file (default) or remote Cloudflare D1",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.target == "d1":
        conn = D1Connection()
    else:
        conn = db.get_connection(config.DB_PATH)
        db.init_schema(conn)

    scrape.main(conn, limit=args.limit)

    count = conn.execute(
        "SELECT COUNT(*) FROM price_history WHERE date = ? AND source = 'daily_scrape'",
        (date.today().isoformat(),),
    ).fetchone()[0]
    print(f"price_history has {count} daily_scrape rows for today")


if __name__ == "__main__":
    main()

#!/usr/bin/env python
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from salecast import backfill, config, db  # noqa: E402
from salecast.clients.d1_client import D1Connection  # noqa: E402
from salecast.clients.itad_client import MissingApiKeyError  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical price data via ITAD")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only backfill the first N tracked games (smoke test)",
    )
    parser.add_argument("--region", type=str, default="US")
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

    try:
        backfill.main(conn, limit=args.limit)
    except MissingApiKeyError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    count = conn.execute(
        "SELECT COUNT(*) FROM price_history WHERE source = 'itad_backfill'"
    ).fetchone()[0]
    print(f"price_history now has {count} itad_backfill rows")


if __name__ == "__main__":
    main()

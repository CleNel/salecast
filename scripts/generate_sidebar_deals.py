#!/usr/bin/env python
"""Generates docs/deals.json - a static snapshot of "Top Deals" and "New
Deals" for the frontend sidebar. Runs after the daily scrape so it reflects
that day's prices, and is deployed as a static asset alongside the rest of
docs/ so the sidebar never depends on the (free-tier, sleep-prone) API."""
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from salecast import config, db  # noqa: E402
from salecast.clients.d1_client import D1Connection  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_PATH = config.PROJECT_ROOT / "docs" / "deals.json"

TOP_DEALS_SQL = """
    SELECT tg.app_id, tg.name, ph.price, ph.discount_pct, ds.composite_score AS deal_score
    FROM deal_scores ds
    JOIN tracked_games tg ON tg.app_id = ds.app_id
    JOIN (
        SELECT app_id, price, discount_pct
        FROM price_history p1
        WHERE date = (SELECT MAX(date) FROM price_history p2 WHERE p2.app_id = p1.app_id)
    ) ph ON ph.app_id = tg.app_id
    WHERE tg.is_free = 0 AND ph.discount_pct > 0
    ORDER BY ds.composite_score DESC
    LIMIT ?
"""

NEW_DEALS_SQL = """
    WITH ranked AS (
        SELECT app_id, price, discount_pct,
               ROW_NUMBER() OVER (PARTITION BY app_id ORDER BY date DESC) AS rn
        FROM price_history
    )
    SELECT tg.app_id, tg.name, cur.price, cur.discount_pct, ds.composite_score AS deal_score
    FROM ranked cur
    JOIN ranked prev ON prev.app_id = cur.app_id AND prev.rn = 2
    JOIN tracked_games tg ON tg.app_id = cur.app_id
    LEFT JOIN deal_scores ds ON ds.app_id = cur.app_id
    WHERE cur.rn = 1
      AND tg.is_free = 0
      AND cur.discount_pct > 0
      AND (prev.discount_pct IS NULL OR prev.discount_pct = 0)
    ORDER BY cur.discount_pct DESC
    LIMIT ?
"""


def _rows_to_games(rows) -> list[dict]:
    games = []
    for row in rows:
        deal_score = row["deal_score"]
        games.append(
            {
                "app_id": row["app_id"],
                "name": row["name"],
                "price": row["price"],
                "discount_pct": row["discount_pct"],
                "deal_score": round(deal_score, 1) if deal_score is not None else None,
            }
        )
    return games


def build_snapshot(conn, limit: int) -> dict:
    top_deals = _rows_to_games(conn.execute(TOP_DEALS_SQL, (limit,)).fetchall())
    new_deals = _rows_to_games(conn.execute(NEW_DEALS_SQL, (limit,)).fetchall())
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "top_deals": top_deals,
        "new_deals": new_deals,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the static Top Deals / New Deals sidebar snapshot")
    parser.add_argument("--target", choices=["sqlite", "d1"], default="sqlite")
    parser.add_argument("--db-path", type=str, default=config.DB_PATH)
    parser.add_argument("--limit", type=int, default=5, help="Games per list")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT_PATH))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    conn = D1Connection() if args.target == "d1" else db.get_connection(args.db_path)
    db.init_schema(conn)

    snapshot = build_snapshot(conn, args.limit)
    logger.info(
        "Built sidebar snapshot: %d top deals, %d new deals",
        len(snapshot["top_deals"]), len(snapshot["new_deals"]),
    )

    output_path = Path(args.output)
    output_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()

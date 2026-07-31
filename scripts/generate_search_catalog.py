#!/usr/bin/env python
"""Generates docs/games_catalog.json - a static snapshot of every non-free
tracked game with the fields the frontend's browse/filter UI needs (genre,
price, discount, deal score, ...). Runs after the daily scrape/deal-score
recompute so it reflects that day's data, and is deployed as a static asset
alongside deals.json so filtering/sorting/scrolling never depends on the
(free-tier, sleep-prone) API - only the single-game detail lookup does."""
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

DEFAULT_OUTPUT_PATH = config.PROJECT_ROOT / "docs" / "games_catalog.json"

CATALOG_SQL = """
    WITH latest_price AS (
        SELECT app_id, price, original_price, discount_pct,
               ROW_NUMBER() OVER (PARTITION BY app_id ORDER BY date DESC) AS rn
        FROM price_history
    )
    SELECT
        tg.app_id, tg.name, tg.genre, tg.publisher, tg.release_date,
        tg.review_count, tg.review_score_pct,
        lp.price, lp.original_price, lp.discount_pct,
        ds.composite_score AS deal_score,
        cl.avg_discount_depth, cl.discount_frequency_per_year
    FROM tracked_games tg
    LEFT JOIN latest_price lp ON lp.app_id = tg.app_id AND lp.rn = 1
    LEFT JOIN deal_scores ds ON ds.app_id = tg.app_id
    LEFT JOIN cluster_labels cl ON cl.app_id = tg.app_id
    WHERE tg.is_free = 0
"""


def _release_year(release_date: str | None) -> int | None:
    if not release_date:
        return None
    try:
        return int(release_date[:4])
    except ValueError:
        return None


def _row_to_game(row) -> dict:
    deal_score = row["deal_score"]
    avg_discount_depth = row["avg_discount_depth"]
    discount_frequency = row["discount_frequency_per_year"]
    return {
        "app_id": row["app_id"],
        "name": row["name"],
        "genre": row["genre"],
        "publisher": row["publisher"],
        "release_year": _release_year(row["release_date"]),
        "review_count": row["review_count"],
        "review_score_pct": row["review_score_pct"],
        "price": row["price"],
        "original_price": row["original_price"],
        "discount_pct": row["discount_pct"] or 0,
        "deal_score": round(deal_score, 1) if deal_score is not None else None,
        "avg_discount_depth": round(avg_discount_depth, 1) if avg_discount_depth is not None else None,
        "discount_frequency_per_year": round(discount_frequency, 1) if discount_frequency is not None else None,
    }


def build_catalog(conn) -> dict:
    rows = conn.execute(CATALOG_SQL).fetchall()
    games = [_row_to_game(row) for row in rows]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "games": games,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the static games_catalog.json browse/filter snapshot")
    parser.add_argument("--target", choices=["sqlite", "d1"], default="sqlite")
    parser.add_argument("--db-path", type=str, default=config.DB_PATH)
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT_PATH))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    conn = D1Connection() if args.target == "d1" else db.get_connection(args.db_path)
    db.init_schema(conn)

    catalog = build_catalog(conn)
    logger.info("Built games catalog: %d non-free games", len(catalog["games"]))

    output_path = Path(args.output)
    # Unlike deals.json (10 rows, indent=2 for readability), this file has
    # one row per tracked game and every visitor's browser downloads it on
    # page load - compact encoding keeps that payload lean.
    output_path.write_text(json.dumps(catalog, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()

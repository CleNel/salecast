#!/usr/bin/env python
import argparse
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from salecast import config, db  # noqa: E402
from salecast.clients.d1_client import D1Connection  # noqa: E402
from salecast.deal_score import compute_deal_scores  # noqa: E402

logger = logging.getLogger(__name__)


def _load_tables(conn) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    tracked_games = pd.DataFrame(
        [dict(row) for row in conn.execute("SELECT * FROM tracked_games").fetchall()]
    )
    price_history = pd.DataFrame(
        [
            dict(row)
            for row in conn.execute("SELECT app_id, date, discount_pct FROM price_history").fetchall()
        ]
    )
    smart_buy_scores = pd.DataFrame(
        [
            dict(row)
            for row in conn.execute(
                "SELECT app_id, target_discount, horizon_days, probability FROM smart_buy_scores"
            ).fetchall()
        ]
    )

    if price_history.empty:
        latest_prices = pd.DataFrame(columns=["app_id", "discount_pct"])
        historical_max = pd.DataFrame(columns=["app_id", "max_discount_pct"])
    else:
        latest_prices = (
            price_history.sort_values("date").groupby("app_id", as_index=False).last()
        )[["app_id", "discount_pct"]]
        historical_max = (
            price_history.groupby("app_id", as_index=False)["discount_pct"]
            .max()
            .rename(columns={"discount_pct": "max_discount_pct"})
        )

    return tracked_games, latest_prices, historical_max, smart_buy_scores


def write_deal_scores(conn, scores: pd.DataFrame, timestamp: str) -> int:
    upsert_sql = """
        INSERT INTO deal_scores (app_id, composite_score, last_updated)
        VALUES (?, ?, ?)
        ON CONFLICT(app_id) DO UPDATE SET
            composite_score = excluded.composite_score,
            last_updated = excluded.last_updated
    """
    statements = [
        (upsert_sql, (int(row.app_id), float(row.deal_score), timestamp))
        for row in scores.itertuples()
    ]

    if hasattr(conn, "execute_batch"):
        return conn.execute_batch(statements)

    changed = 0
    for sql, params in statements:
        changed += conn.execute(sql, params).rowcount
    conn.commit()
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute the composite deal score for every tracked game")
    parser.add_argument(
        "--target", choices=["sqlite", "d1"], default="sqlite",
        help="Storage backend to read from and write deal_scores to",
    )
    parser.add_argument(
        "--db-path", type=str, default=config.DB_PATH,
        help="Local SQLite file to use when --target=sqlite (e.g. a snapshot for offline analysis)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.target == "d1":
        conn = D1Connection()
    else:
        conn = db.get_connection(args.db_path)
    db.init_schema(conn)

    tracked_games, latest_prices, historical_max, smart_buy_scores = _load_tables(conn)
    scores = compute_deal_scores(tracked_games, latest_prices, historical_max, smart_buy_scores)
    logger.info(
        "Computed deal scores for %d games (mean=%.1f, min=%.1f, max=%.1f)",
        len(scores), scores["deal_score"].mean(), scores["deal_score"].min(), scores["deal_score"].max(),
    )

    timestamp = datetime.now(timezone.utc).isoformat()
    changed = write_deal_scores(conn, scores, timestamp)
    logger.info("Wrote %d deal_scores rows", changed)

    count = conn.execute("SELECT COUNT(*) FROM deal_scores").fetchone()[0]
    print(f"deal_scores now has {count} rows (as of {date.today().isoformat()})")


if __name__ == "__main__":
    main()

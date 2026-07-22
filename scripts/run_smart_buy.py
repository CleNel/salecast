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
from salecast.labels import build_scoring_examples, build_training_examples  # noqa: E402
from salecast.smart_buy import score_games, train_and_evaluate  # noqa: E402

logger = logging.getLogger(__name__)


def _load_tables(conn) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    tracked_games = pd.DataFrame(
        [dict(row) for row in conn.execute("SELECT * FROM tracked_games").fetchall()]
    )
    price_history = pd.DataFrame(
        [
            dict(row)
            for row in conn.execute(
                "SELECT app_id, date, price, discount_pct, source FROM price_history"
            ).fetchall()
        ]
    )
    cluster_labels = pd.DataFrame(
        [dict(row) for row in conn.execute("SELECT app_id, cluster_id FROM cluster_labels").fetchall()]
    )
    return tracked_games, price_history, cluster_labels


def write_smart_buy_scores(conn, scores: pd.DataFrame, timestamp: str) -> int:
    upsert_sql = """
        INSERT INTO smart_buy_scores (app_id, target_discount, horizon_days, probability, last_updated)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(app_id, target_discount, horizon_days) DO UPDATE SET
            probability = excluded.probability,
            last_updated = excluded.last_updated
    """
    statements = [
        (
            upsert_sql,
            (int(row.app_id), int(row.target_discount), int(row.horizon_days), float(row.probability), timestamp),
        )
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
    parser = argparse.ArgumentParser(description="Train the smart-buy model and score tracked games")
    parser.add_argument(
        "--target", choices=["sqlite", "d1"], default="sqlite",
        help="Storage backend to read from and write smart_buy_scores to",
    )
    parser.add_argument(
        "--db-path", type=str, default=config.DB_PATH,
        help="Local SQLite file to use when --target=sqlite (e.g. a snapshot for offline analysis)",
    )
    parser.add_argument(
        "--model", choices=["logistic_regression", "random_forest"], default=None,
        help="Force a specific model instead of picking the higher ROC AUC on the held-out split",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.target == "d1":
        conn = D1Connection()
    else:
        conn = db.get_connection(args.db_path)
    db.init_schema(conn)

    tracked_games, price_history, cluster_labels = _load_tables(conn)

    examples = build_training_examples(price_history, tracked_games, cluster_labels)
    logger.info("Built %d training examples across %d games", len(examples), examples["app_id"].nunique())

    results = train_and_evaluate(examples)
    for name, r in results.items():
        logger.info(
            "%s: n_train=%d n_test=%d precision=%.3f recall=%.3f f1=%.3f roc_auc=%.3f avg_precision=%.3f",
            name, r["n_train"], r["n_test"], r["precision"], r["recall"], r["f1"],
            r["roc_auc"], r["avg_precision"],
        )
        logger.info("%s top features: %s", name, r["feature_importances"].head(8).round(3).to_dict())

    chosen_name = args.model or max(results, key=lambda name: results[name]["roc_auc"])
    logger.info("Chosen model: %s", chosen_name)

    scoring_examples = build_scoring_examples(price_history, tracked_games, cluster_labels)
    scores = score_games(results[chosen_name]["pipeline"], scoring_examples)

    timestamp = datetime.now(timezone.utc).isoformat()
    changed = write_smart_buy_scores(conn, scores, timestamp)
    logger.info("Wrote %d smart_buy_scores rows", changed)

    count = conn.execute("SELECT COUNT(*) FROM smart_buy_scores").fetchone()[0]
    print(f"smart_buy_scores now has {count} rows (model={chosen_name}, as of {date.today().isoformat()})")


if __name__ == "__main__":
    main()

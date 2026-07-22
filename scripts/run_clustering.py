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
from salecast.clustering import cluster_games, write_cluster_labels  # noqa: E402
from salecast.features import FEATURE_COLUMNS, build_game_features  # noqa: E402
from salecast.visualize import plot_clusters  # noqa: E402

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cluster tracked games by discounting behavior")
    parser.add_argument("--k", type=int, default=None, help="Force a specific k (skip auto-selection)")
    parser.add_argument(
        "--target", choices=["sqlite", "d1"], default="sqlite",
        help="Storage backend to read price history from and write cluster_labels to",
    )
    parser.add_argument(
        "--db-path", type=str, default=config.DB_PATH,
        help="Local SQLite file to use when --target=sqlite (e.g. a snapshot for offline analysis)",
    )
    parser.add_argument(
        "--plot", type=str, default=str(config.PROJECT_ROOT / "reports" / "cluster_visualization.png"),
        help="Path to save the PCA scatter plot (set to '' to skip plotting)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.target == "d1":
        conn = D1Connection()
    else:
        conn = db.get_connection(args.db_path)
        db.init_schema(conn)

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

    features = build_game_features(price_history, tracked_games)
    logger.info(
        "%d/%d tracked games have enough discount history to cluster",
        len(features), len(tracked_games),
    )

    labeled, k, k_scores = cluster_games(features, k=args.k)
    logger.info("k=%d chosen (silhouette scores considered: %s)", k, k_scores)

    for cluster_id, group in labeled.groupby("cluster_id"):
        top_publishers = group["publisher"].value_counts().head(3).to_dict()
        means = group[FEATURE_COLUMNS].mean().round(1).to_dict()
        logger.info(
            "cluster %d: n=%d, top publishers=%s, feature means=%s",
            cluster_id, len(group), top_publishers, means,
        )

    timestamp = datetime.now(timezone.utc).isoformat()
    changed = write_cluster_labels(conn, labeled, timestamp)
    logger.info("Wrote %d cluster_labels rows", changed)

    if args.plot:
        Path(args.plot).parent.mkdir(parents=True, exist_ok=True)
        plot_clusters(labeled, args.plot)
        logger.info("Saved cluster visualization to %s", args.plot)

    count = conn.execute("SELECT COUNT(*) FROM cluster_labels").fetchone()[0]
    print(f"cluster_labels now has {count} rows (k={k}, as of {date.today().isoformat()})")


if __name__ == "__main__":
    main()

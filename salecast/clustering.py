from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from salecast.features import FEATURE_COLUMNS

DEFAULT_K_RANGE = range(2, 11)

# Silhouette score alone will happily pick a k that just isolates a single
# extreme outlier as its own "cluster" (seen with k=5 on real data: one game
# with a discount-depth trend far outside the rest split off by itself).
# Skipping k candidates whose smallest cluster falls below this floor keeps
# auto-selection from choosing degenerate near-singleton clusters.
MIN_CLUSTER_SIZE = 10


def score_k_candidates(
    X: np.ndarray, k_range: range = DEFAULT_K_RANGE, random_state: int = 42
) -> dict[int, float]:
    """Fits K-means for each k in k_range and returns {k: silhouette_score},
    excluding any k whose smallest resulting cluster is below MIN_CLUSTER_SIZE."""
    scores = {}
    for k in k_range:
        labels = KMeans(n_clusters=k, random_state=random_state, n_init=10).fit_predict(X)
        if np.bincount(labels).min() < MIN_CLUSTER_SIZE:
            continue
        scores[k] = silhouette_score(X, labels)
    return scores


def cluster_games(
    features: pd.DataFrame,
    k: int | None = None,
    k_range: range = DEFAULT_K_RANGE,
    random_state: int = 42,
) -> tuple[pd.DataFrame, int, dict[int, float]]:
    """Standardizes FEATURE_COLUMNS and runs K-means. If k is None, picks the
    k in k_range with the highest silhouette score. Returns
    (features with a 'cluster_id' column added, chosen k, {k: silhouette_score})."""
    X = StandardScaler().fit_transform(features[FEATURE_COLUMNS])

    k_scores = score_k_candidates(X, k_range=k_range, random_state=random_state)
    if k is None:
        if not k_scores:
            raise ValueError(
                f"No k in {k_range} produced a cluster of at least "
                f"MIN_CLUSTER_SIZE={MIN_CLUSTER_SIZE}; pass k explicitly"
            )
        k = max(k_scores, key=k_scores.get)

    model = KMeans(n_clusters=k, random_state=random_state, n_init=10)
    labeled = features.copy()
    labeled["cluster_id"] = model.fit_predict(X)
    return labeled, k, k_scores


def write_cluster_labels(conn: Any, labeled: pd.DataFrame, timestamp: str) -> int:
    """Upserts one (app_id, cluster_id, last_updated) row per labeled game
    into cluster_labels. Uses D1Connection.execute_batch() when available
    (a single HTTP round-trip) instead of looping execute() per row."""
    upsert_sql = """
        INSERT INTO cluster_labels (app_id, cluster_id, last_updated)
        VALUES (?, ?, ?)
        ON CONFLICT(app_id) DO UPDATE SET
            cluster_id = excluded.cluster_id,
            last_updated = excluded.last_updated
    """
    statements = [
        (upsert_sql, (int(row.app_id), int(row.cluster_id), timestamp))
        for row in labeled.itertuples()
    ]

    if hasattr(conn, "execute_batch"):
        return conn.execute_batch(statements)

    changed = 0
    for sql, params in statements:
        changed += conn.execute(sql, params).rowcount
    conn.commit()
    return changed

import sqlite3

import numpy as np
import pandas as pd

from salecast import db
from salecast.clustering import (
    MIN_CLUSTER_SIZE,
    cluster_games,
    score_k_candidates,
    write_cluster_labels,
)
from salecast.features import FEATURE_COLUMNS


def _synthetic_features(n_per_cluster=20):
    rng = np.random.default_rng(0)
    cluster_a = rng.normal(loc=0, scale=0.5, size=(n_per_cluster, len(FEATURE_COLUMNS)))
    cluster_b = rng.normal(loc=20, scale=0.5, size=(n_per_cluster, len(FEATURE_COLUMNS)))
    data = np.vstack([cluster_a, cluster_b])
    df = pd.DataFrame(data, columns=FEATURE_COLUMNS)
    df["app_id"] = range(len(df))
    return df


def test_cluster_games_recovers_two_well_separated_clusters():
    features = _synthetic_features()

    labeled, k, scores = cluster_games(features, k_range=range(2, 6))

    assert k == 2
    first_half_ids = set(labeled["cluster_id"].iloc[:20])
    second_half_ids = set(labeled["cluster_id"].iloc[20:])
    assert len(first_half_ids) == 1
    assert len(second_half_ids) == 1
    assert first_half_ids != second_half_ids


def test_cluster_games_respects_explicit_k():
    features = _synthetic_features()

    labeled, k, scores = cluster_games(features, k=3, k_range=range(2, 6))

    assert k == 3
    assert labeled["cluster_id"].nunique() == 3


def test_score_k_candidates_excludes_k_below_min_cluster_size():
    # A tiny outlier point next to a big blob: k=2 would isolate the outlier
    # as a singleton cluster, so it should be excluded from the scores.
    rng = np.random.default_rng(0)
    blob = rng.normal(loc=0, scale=0.1, size=(MIN_CLUSTER_SIZE * 5, len(FEATURE_COLUMNS)))
    outlier = np.full((1, len(FEATURE_COLUMNS)), 100.0)
    X = np.vstack([blob, outlier])

    scores = score_k_candidates(X, k_range=range(2, 4))

    assert 2 not in scores


class _FakeD1Conn:
    def __init__(self):
        self.batches = []

    def execute_batch(self, statements):
        self.batches.append(statements)
        return len(statements)


def _labeled_fixture(app_ids, cluster_ids):
    data = {"app_id": app_ids, "cluster_id": cluster_ids}
    for i, column in enumerate(FEATURE_COLUMNS):
        data[column] = [10.0 * i + j for j in range(len(app_ids))]
    return pd.DataFrame(data)


def test_write_cluster_labels_uses_execute_batch_when_available():
    labeled = _labeled_fixture([1, 2], [0, 1])
    conn = _FakeD1Conn()

    changed = write_cluster_labels(conn, labeled, "2026-07-22T00:00:00Z")

    assert changed == 2
    assert len(conn.batches) == 1
    assert len(conn.batches[0]) == 2


def test_write_cluster_labels_falls_back_to_execute_loop():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)
    conn.execute(
        "INSERT INTO tracked_games (app_id, name, first_tracked_date) VALUES (1, 'G', '2020-01-01')"
    )
    conn.commit()

    labeled = _labeled_fixture([1], [0])
    changed = write_cluster_labels(conn, labeled, "2026-07-22T00:00:00Z")

    assert changed == 1
    row = conn.execute(
        "SELECT cluster_id, avg_discount_depth FROM cluster_labels WHERE app_id = 1"
    ).fetchone()
    assert row["cluster_id"] == 0
    assert row["avg_discount_depth"] == 0.0


def test_write_cluster_labels_upserts_on_conflict():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)
    conn.execute(
        "INSERT INTO tracked_games (app_id, name, first_tracked_date) VALUES (1, 'G', '2020-01-01')"
    )
    conn.commit()

    write_cluster_labels(conn, _labeled_fixture([1], [0]), "2026-01-01T00:00:00Z")
    write_cluster_labels(conn, _labeled_fixture([1], [2]), "2026-07-22T00:00:00Z")

    rows = conn.execute("SELECT cluster_id, last_updated FROM cluster_labels").fetchall()
    assert len(rows) == 1
    assert rows[0]["cluster_id"] == 2
    assert rows[0]["last_updated"] == "2026-07-22T00:00:00Z"

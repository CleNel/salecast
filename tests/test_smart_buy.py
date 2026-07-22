import numpy as np
import pandas as pd

from salecast.labels import FEATURE_COLUMNS
from salecast.smart_buy import (
    ALL_MODEL_FEATURES,
    bucket_publishers,
    build_preprocessor,
    score_games,
    split_by_game,
    train_and_evaluate,
)


def test_bucket_publishers_keeps_top_n_and_buckets_the_rest():
    publisher = pd.Series(["A"] * 5 + ["B"] * 3 + ["C"] * 1 + [None])

    bucketed = bucket_publishers(publisher, top_n=2)

    assert set(bucketed.iloc[:5]) == {"A"}
    assert set(bucketed.iloc[5:8]) == {"B"}
    assert bucketed.iloc[8] == "Other"
    assert bucketed.iloc[9] == "Unknown"


def test_split_by_game_has_no_overlapping_app_ids():
    examples = pd.DataFrame({"app_id": np.repeat(np.arange(20), 5), "label": np.random.randint(0, 2, 100)})

    train, test = split_by_game(examples, test_size=0.25, random_state=0)

    assert set(train["app_id"]).isdisjoint(set(test["app_id"]))
    assert len(train) + len(test) == len(examples)


def _synthetic_examples(n_games=60, obs_per_game=6, random_state=0):
    rng = np.random.default_rng(random_state)
    rows = []
    for app_id in range(n_games):
        genre = rng.choice(["Action", "Indie", "Strategy"])
        publisher = rng.choice(["Pub A", "Pub B", "Pub C", "Pub D", "Pub E", "Pub F"])
        cluster_id = rng.choice([0, 1, 2])
        for _ in range(obs_per_game):
            days_since_last_discount = rng.uniform(0, 400)
            # Make the label strongly (but not perfectly) dependent on
            # days_since_last_discount so a model has real signal to learn.
            label = int(days_since_last_discount < 150 and rng.random() < 0.85)
            rows.append(
                {
                    "app_id": app_id,
                    "target_discount": rng.choice([30, 50, 70]),
                    "horizon_days": rng.choice([14, 30, 60]),
                    "days_since_release": rng.uniform(30, 2000),
                    "days_since_last_discount": days_since_last_discount,
                    "ever_discounted": 1,
                    "current_discount": rng.choice([0, 10, 25, 50]),
                    "days_until_next_sale_window": rng.uniform(0, 180),
                    "cluster_id": cluster_id,
                    "review_score_pct": rng.uniform(50, 99),
                    "genre": genre,
                    "publisher": publisher,
                    "label": label,
                }
            )
    return pd.DataFrame(rows)


def test_build_preprocessor_produces_numeric_output():
    examples = _synthetic_examples()
    from salecast.smart_buy import _add_publisher_bucket

    examples = _add_publisher_bucket(examples)
    transformed = build_preprocessor().fit_transform(examples[ALL_MODEL_FEATURES])

    assert transformed.shape[0] == len(examples)


def test_train_and_evaluate_returns_metrics_for_both_models():
    examples = _synthetic_examples()

    results = train_and_evaluate(examples, random_state=0)

    assert set(results.keys()) == {"logistic_regression", "random_forest"}
    for r in results.values():
        assert 0.0 <= r["roc_auc"] <= 1.0
        assert r["n_train"] + r["n_test"] == len(examples)
        assert set(r["feature_importances"].index) == set(
            r["pipeline"].named_steps["preprocess"].get_feature_names_out()
        )


def test_train_and_evaluate_learns_the_synthetic_signal():
    examples = _synthetic_examples(n_games=100, obs_per_game=8)

    results = train_and_evaluate(examples, random_state=0)

    # days_since_last_discount was constructed to be strongly predictive -
    # a model that learned anything should beat random guessing by a clear margin.
    assert results["random_forest"]["roc_auc"] > 0.7


def test_score_games_returns_one_probability_per_row():
    examples = _synthetic_examples()
    results = train_and_evaluate(examples, random_state=0)
    pipeline = results["random_forest"]["pipeline"]

    scoring_examples = examples[["app_id"] + FEATURE_COLUMNS + ["genre", "publisher"]].head(10)
    scored = score_games(pipeline, scoring_examples)

    assert len(scored) == 10
    assert (scored["probability"] >= 0).all() and (scored["probability"] <= 1).all()
    assert list(scored.columns) == ["app_id", "target_discount", "horizon_days", "probability"]

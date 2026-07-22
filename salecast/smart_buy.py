import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from salecast.labels import FEATURE_COLUMNS

NUMERIC_FEATURES = [c for c in FEATURE_COLUMNS if c != "cluster_id"]
CATEGORICAL_FEATURES = ["cluster_id", "genre", "publisher_bucket"]
ALL_MODEL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Publisher is high-cardinality (hundreds of distinct values, many appearing
# only once or twice) - one-hot encoding all of them would let a linear
# model overfit to single-game publisher dummies. Bucketing to the most
# frequent publishers plus "Other" keeps the category count sane while
# still letting well-represented publishers (EA, Ubisoft, Valve, ...)
# carry their own signal.
TOP_PUBLISHER_COUNT = 20


def bucket_publishers(publisher: pd.Series, top_n: int = TOP_PUBLISHER_COUNT) -> pd.Series:
    top = publisher.value_counts().head(top_n).index
    bucketed = publisher.where(publisher.isin(top), "Other")
    return bucketed.where(publisher.notna(), "Unknown")


def _add_publisher_bucket(examples: pd.DataFrame) -> pd.DataFrame:
    examples = examples.copy()
    examples["publisher_bucket"] = bucket_publishers(examples["publisher"])
    return examples


def build_preprocessor() -> ColumnTransformer:
    numeric = Pipeline(
        [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
    )
    categorical = Pipeline(
        [
            ("impute", SimpleImputer(strategy="constant", fill_value="missing")),
            ("encode", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    return ColumnTransformer(
        [
            ("numeric", numeric, NUMERIC_FEATURES),
            ("categorical", categorical, CATEGORICAL_FEATURES),
        ]
    )


def split_by_game(
    examples: pd.DataFrame, test_size: float = 0.2, random_state: int = 42
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Splits by app_id (not row) so no game's observations leak across the
    train/test boundary - a row-level split would let the model memorize a
    game's own discounting pattern from one time slice and "predict" it on
    another, overstating how well it generalizes to unseen games."""
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
    train_idx, test_idx = next(splitter.split(examples, groups=examples["app_id"]))
    return examples.iloc[train_idx], examples.iloc[test_idx]


def _build_models(random_state: int) -> dict:
    return {
        "logistic_regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
        "random_forest": RandomForestClassifier(
            n_estimators=300, max_depth=8, random_state=random_state, class_weight="balanced"
        ),
    }


def _feature_importances(pipeline: Pipeline) -> pd.Series:
    names = pipeline.named_steps["preprocess"].get_feature_names_out()
    model = pipeline.named_steps["model"]
    if hasattr(model, "coef_"):
        values = model.coef_[0]
    else:
        values = model.feature_importances_
    return pd.Series(values, index=names).sort_values(key=abs, ascending=False)


def train_and_evaluate(examples: pd.DataFrame, random_state: int = 42) -> dict:
    """Trains logistic regression and random forest on a game-level train
    split, evaluates both on the held-out games, and returns a fitted
    pipeline + metrics + feature importances per model."""
    examples = _add_publisher_bucket(examples)
    train, test = split_by_game(examples, random_state=random_state)

    results = {}
    for name, model in _build_models(random_state).items():
        pipeline = Pipeline([("preprocess", build_preprocessor()), ("model", model)])
        pipeline.fit(train[ALL_MODEL_FEATURES], train["label"])

        probs = pipeline.predict_proba(test[ALL_MODEL_FEATURES])[:, 1]
        preds = (probs >= 0.5).astype(int)
        precision, recall, f1, _ = precision_recall_fscore_support(
            test["label"], preds, average="binary", zero_division=0
        )

        results[name] = {
            "pipeline": pipeline,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "roc_auc": roc_auc_score(test["label"], probs),
            "avg_precision": average_precision_score(test["label"], probs),
            "feature_importances": _feature_importances(pipeline),
            "n_train": len(train),
            "n_test": len(test),
        }
    return results


def score_games(pipeline: Pipeline, scoring_examples: pd.DataFrame) -> pd.DataFrame:
    """Applies a fitted pipeline to build_scoring_examples() output. Returns
    scoring_examples' app_id/target_discount/horizon_days plus a
    'probability' column."""
    examples = _add_publisher_bucket(scoring_examples)
    probs = pipeline.predict_proba(examples[ALL_MODEL_FEATURES])[:, 1]
    return pd.DataFrame(
        {
            "app_id": examples["app_id"].values,
            "target_discount": examples["target_discount"].values,
            "horizon_days": examples["horizon_days"].values,
            "probability": probs,
        }
    )

import pandas as pd
import pytest

from salecast.features import FEATURE_COLUMNS, MIN_DISCOUNT_EVENTS, build_game_features


def _tracked_games(rows):
    return pd.DataFrame(rows, columns=["app_id", "release_date"])


def test_build_game_features_computes_expected_values():
    tracked_games = _tracked_games([(1, "2020-01-01")])
    price_history = pd.DataFrame(
        [
            {"app_id": 1, "date": "2020-01-15", "price": 59.99, "discount_pct": 0, "source": "s"},
            {"app_id": 1, "date": "2020-04-01", "price": 53.99, "discount_pct": 10, "source": "s"},
            {"app_id": 1, "date": "2020-07-01", "price": 47.99, "discount_pct": 20, "source": "s"},
            {"app_id": 1, "date": "2021-01-01", "price": 41.99, "discount_pct": 30, "source": "s"},
        ]
    )

    features = build_game_features(price_history, tracked_games)

    assert len(features) == 1
    row = features.iloc[0]
    assert row["avg_discount_depth"] == pytest.approx(20.0)
    assert row["discount_depth_std"] == pytest.approx(10.0)
    assert row["num_discount_events"] == 3
    assert row["time_to_first_discount_days"] == 91
    # 2020-01-01 to 2021-01-01 is 366 days (2020 is a leap year)
    assert row["discount_frequency_per_year"] == pytest.approx(3 / ((366 - 91) / 365.25))
    assert row["discount_depth_trend"] == pytest.approx(25.5882, abs=1e-3)


def test_build_game_features_drops_games_below_min_discount_events():
    assert MIN_DISCOUNT_EVENTS >= 2  # sanity-check the fixture below actually exercises the drop

    tracked_games = _tracked_games([(1, "2020-01-01"), (2, "2020-01-01")])
    price_history = pd.DataFrame(
        [
            # app 1: only one discount event - below MIN_DISCOUNT_EVENTS, should be dropped
            {"app_id": 1, "date": "2020-04-01", "price": 53.99, "discount_pct": 10, "source": "s"},
            # app 2: enough discount events - should survive
            {"app_id": 2, "date": "2020-04-01", "price": 53.99, "discount_pct": 10, "source": "s"},
            {"app_id": 2, "date": "2020-07-01", "price": 47.99, "discount_pct": 20, "source": "s"},
            {"app_id": 2, "date": "2021-01-01", "price": 41.99, "discount_pct": 30, "source": "s"},
        ]
    )

    features = build_game_features(price_history, tracked_games)

    assert list(features["app_id"]) == [2]


def test_build_game_features_ignores_non_discount_rows():
    tracked_games = _tracked_games([(1, "2020-01-01")])
    price_history = pd.DataFrame(
        [
            {"app_id": 1, "date": d, "price": 59.99, "discount_pct": 0, "source": "s"}
            for d in ["2020-02-01", "2020-03-01", "2020-04-01", "2020-05-01", "2020-06-01"]
        ]
        + [
            {"app_id": 1, "date": "2020-07-01", "price": 53.99, "discount_pct": 10, "source": "s"},
            {"app_id": 1, "date": "2020-08-01", "price": 47.99, "discount_pct": 20, "source": "s"},
            {"app_id": 1, "date": "2020-09-01", "price": 41.99, "discount_pct": 30, "source": "s"},
        ]
    )

    features = build_game_features(price_history, tracked_games)

    assert len(features) == 1
    assert features.iloc[0]["num_discount_events"] == 3


def test_build_game_features_returns_all_feature_columns():
    tracked_games = _tracked_games([(1, "2020-01-01")])
    price_history = pd.DataFrame(
        [
            {"app_id": 1, "date": "2020-04-01", "price": 53.99, "discount_pct": 10, "source": "s"},
            {"app_id": 1, "date": "2020-07-01", "price": 47.99, "discount_pct": 20, "source": "s"},
            {"app_id": 1, "date": "2021-01-01", "price": 41.99, "discount_pct": 30, "source": "s"},
        ]
    )

    features = build_game_features(price_history, tracked_games)

    for column in FEATURE_COLUMNS:
        assert column in features.columns

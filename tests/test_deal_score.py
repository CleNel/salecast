import pandas as pd
import pytest

from salecast.deal_score import (
    CANONICAL_HORIZON_DAYS,
    CANONICAL_TARGET_DISCOUNT,
    compute_deal_scores,
    compute_discount_ratio,
    wilson_lower_bound,
)


def test_wilson_lower_bound_penalizes_small_samples():
    small_perfect_sample = wilson_lower_bound(pd.Series([5]), pd.Series([5])).iloc[0]
    large_strong_sample = wilson_lower_bound(pd.Series([9500]), pd.Series([10000])).iloc[0]

    # 5/5 (100%) should rank below 9500/10000 (95%) once sample size is
    # accounted for - a handful of perfect reviews shouldn't outrank a
    # huge, very-well-reviewed game.
    assert small_perfect_sample < large_strong_sample
    assert small_perfect_sample == pytest.approx(0.5655, abs=1e-3)
    assert large_strong_sample == pytest.approx(0.9456, abs=1e-3)


def test_wilson_lower_bound_handles_zero_reviews():
    assert wilson_lower_bound(pd.Series([0]), pd.Series([0])).iloc[0] == 0.0


def test_compute_discount_ratio_relative_to_own_history():
    ratio = compute_discount_ratio(pd.Series([50, 90, 0]), pd.Series([100, 90, 0]))

    assert ratio.iloc[0] == pytest.approx(0.5)
    assert ratio.iloc[1] == pytest.approx(1.0)
    assert ratio.iloc[2] == 0.0  # never discounted at all - no divide-by-zero


def test_compute_deal_scores_ranks_deep_discount_above_no_discount():
    tracked_games = pd.DataFrame(
        {
            "app_id": [1, 2],
            "review_count": [10000, 10000],
            "review_score_pct": [90.0, 90.0],
        }
    )
    latest_prices = pd.DataFrame({"app_id": [1, 2], "discount_pct": [80, 0]})
    historical_max = pd.DataFrame({"app_id": [1, 2], "max_discount_pct": [80, 50]})
    smart_buy_scores = pd.DataFrame(
        {
            "app_id": [1, 1, 2, 2],
            "target_discount": [CANONICAL_TARGET_DISCOUNT, 30, CANONICAL_TARGET_DISCOUNT, 30],
            "horizon_days": [CANONICAL_HORIZON_DAYS, 14, CANONICAL_HORIZON_DAYS, 14],
            "probability": [0.9, 0.5, 0.1, 0.5],
        }
    )

    scores = compute_deal_scores(tracked_games, latest_prices, historical_max, smart_buy_scores)

    game_1 = scores[scores["app_id"] == 1].iloc[0]
    game_2 = scores[scores["app_id"] == 2].iloc[0]
    assert game_1["deal_score"] > game_2["deal_score"]
    assert game_1["discount_ratio"] == pytest.approx(1.0)
    assert game_2["discount_ratio"] == 0.0


def test_compute_deal_scores_only_uses_canonical_scenario():
    tracked_games = pd.DataFrame({"app_id": [1], "review_count": [100], "review_score_pct": [90.0]})
    latest_prices = pd.DataFrame({"app_id": [1], "discount_pct": [50]})
    historical_max = pd.DataFrame({"app_id": [1], "max_discount_pct": [50]})
    smart_buy_scores = pd.DataFrame(
        {
            "app_id": [1, 1],
            "target_discount": [CANONICAL_TARGET_DISCOUNT, 70],
            "horizon_days": [CANONICAL_HORIZON_DAYS, 60],
            "probability": [0.8, 0.1],
        }
    )

    scores = compute_deal_scores(tracked_games, latest_prices, historical_max, smart_buy_scores)

    assert scores.iloc[0]["smart_buy_probability"] == pytest.approx(0.8)


def test_compute_deal_scores_fills_missing_data_with_zero():
    tracked_games = pd.DataFrame({"app_id": [1], "review_count": [0], "review_score_pct": [None]})
    latest_prices = pd.DataFrame(columns=["app_id", "discount_pct"])
    historical_max = pd.DataFrame(columns=["app_id", "max_discount_pct"])
    smart_buy_scores = pd.DataFrame(columns=["app_id", "target_discount", "horizon_days", "probability"])

    scores = compute_deal_scores(tracked_games, latest_prices, historical_max, smart_buy_scores)

    row = scores.iloc[0]
    assert row["deal_score"] == 0.0
    assert row["discount_ratio"] == 0.0
    assert row["smart_buy_probability"] == 0.0
    assert row["review_confidence"] == 0.0

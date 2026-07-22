import numpy as np
import pandas as pd

# Hand-weighted v1 composite (see steam-smart-buy-plan.md section 7 - a
# learned ranking model is the stretch goal, not this). Tunable, but
# defensible as-is: discount_ratio carries the most weight since "is this
# actually close to this game's own best discount" is the most direct
# answer to "is this a good deal", with smart_buy_probability and review
# confidence adjusting it.
WEIGHTS = {
    "discount_ratio": 0.40,
    "smart_buy_probability": 0.35,
    "review_confidence": 0.25,
}

# The smart-buy scenario blended into the deal score's "is now a good
# moment" component - the middle-ground 50%-off/30-day definition. The
# other two scenarios (30%/14d, 70%/60d) stay available individually via
# smart_buy_scores but aren't folded into this single composite number.
CANONICAL_TARGET_DISCOUNT = 50
CANONICAL_HORIZON_DAYS = 30


def wilson_lower_bound(positive: pd.Series, total: pd.Series, z: float = 1.96) -> pd.Series:
    """Wilson score interval lower bound for the true positive rate. Ranks a
    well-reviewed game with many reviews above one with a higher raw
    average but far fewer reviews, instead of taking review_score_pct at
    face value (where 5/5 positive would outrank 9,500/10,000)."""
    total = total.astype(float).replace(0, np.nan)
    p = positive / total
    z2 = z * z
    center = p + z2 / (2 * total)
    margin = z * np.sqrt((p * (1 - p) + z2 / (4 * total)) / total)
    denom = 1 + z2 / total
    return ((center - margin) / denom).fillna(0.0).clip(lower=0.0, upper=1.0)


def compute_discount_ratio(current_discount: pd.Series, historical_max_discount: pd.Series) -> pd.Series:
    """current_discount as a fraction of this game's own best-ever discount
    - a 30% discount means very different things for a game that tops out
    at 40% off versus one that regularly hits 90% off."""
    safe_max = historical_max_discount.astype(float).replace(0, np.nan)
    ratio = current_discount.astype(float) / safe_max
    return ratio.fillna(0.0).clip(lower=0.0, upper=1.0)


def compute_deal_scores(
    tracked_games: pd.DataFrame,
    latest_prices: pd.DataFrame,
    historical_max_discount: pd.DataFrame,
    smart_buy_scores: pd.DataFrame,
) -> pd.DataFrame:
    """Combines discount depth (relative to each game's own history),
    the smart-buy model's probability, and a review-confidence score into
    one 0-100 composite deal_score per app_id.

    tracked_games: app_id, review_count, review_score_pct
    latest_prices: app_id, discount_pct (most recent price_history row)
    historical_max_discount: app_id, max_discount_pct (MAX(discount_pct)
        ever recorded for this game)
    smart_buy_scores: app_id, target_discount, horizon_days, probability
        (only CANONICAL_TARGET_DISCOUNT/CANONICAL_HORIZON_DAYS rows used)
    """
    games = tracked_games[["app_id", "review_count", "review_score_pct"]].copy()

    games = games.merge(latest_prices[["app_id", "discount_pct"]], on="app_id", how="left")
    games["discount_pct"] = pd.to_numeric(games["discount_pct"], errors="coerce").fillna(0)

    games = games.merge(
        historical_max_discount[["app_id", "max_discount_pct"]], on="app_id", how="left"
    )
    games["max_discount_pct"] = pd.to_numeric(games["max_discount_pct"], errors="coerce").fillna(0)

    canonical = smart_buy_scores[
        (smart_buy_scores["target_discount"] == CANONICAL_TARGET_DISCOUNT)
        & (smart_buy_scores["horizon_days"] == CANONICAL_HORIZON_DAYS)
    ][["app_id", "probability"]]
    games = games.merge(canonical, on="app_id", how="left")
    games["probability"] = pd.to_numeric(games["probability"], errors="coerce").fillna(0.0)

    games["discount_ratio"] = compute_discount_ratio(games["discount_pct"], games["max_discount_pct"])

    review_score_pct = pd.to_numeric(games["review_score_pct"], errors="coerce").fillna(0.0)
    review_count = pd.to_numeric(games["review_count"], errors="coerce").fillna(0).astype(int)
    positive = (review_score_pct / 100 * review_count).round()
    games["review_confidence"] = wilson_lower_bound(positive, review_count)

    games["smart_buy_probability"] = games["probability"]

    games["deal_score"] = 100 * (
        WEIGHTS["discount_ratio"] * games["discount_ratio"]
        + WEIGHTS["smart_buy_probability"] * games["smart_buy_probability"]
        + WEIGHTS["review_confidence"] * games["review_confidence"]
    )

    return games[
        [
            "app_id", "deal_score", "discount_ratio", "smart_buy_probability",
            "review_confidence", "discount_pct", "max_discount_pct",
        ]
    ]

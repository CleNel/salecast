import numpy as np
import pandas as pd

# A game needs at least this many discount events before trend/variance
# features are meaningful - below this, we can't tell "erratic" from "no
# data yet", so these games are excluded from clustering rather than
# imputed with a misleading placeholder.
MIN_DISCOUNT_EVENTS = 3

FEATURE_COLUMNS = [
    "avg_discount_depth",
    "discount_depth_std",
    "discount_frequency_per_year",
    "time_to_first_discount_days",
    "discount_depth_trend",
]


# A game whose only discount events fall within a short window (a few
# events over a handful of weeks) gets a least-squares slope fit to very
# little data, then annualized (x365.25) - a modest swing over a few weeks
# extrapolates into an absurd "percent per year" figure (seen in practice:
# a game with 4 discount events across ~6 weeks produced a 451%/year
# "trend"). discount_pct itself only ever ranges 0-100, so no annualized
# rate beyond that range can be a real signal - clip to it instead of
# letting the extrapolation distort clustering and visualizations.
MAX_ABS_TREND_PCT_PER_YEAR = 100.0


def _slope_per_year(days_since_release: pd.Series, discount_pct: pd.Series) -> float:
    """Least-squares slope of discount_pct per year of days_since_release -
    positive means discounts have been getting deeper over time. Clipped to
    +/-MAX_ABS_TREND_PCT_PER_YEAR (see comment above)."""
    if days_since_release.nunique() < 2:
        return np.nan
    slope_per_day, _ = np.polyfit(days_since_release, discount_pct, 1)
    slope_per_year = slope_per_day * 365.25
    return float(np.clip(slope_per_year, -MAX_ABS_TREND_PCT_PER_YEAR, MAX_ABS_TREND_PCT_PER_YEAR))


def build_game_features(price_history: pd.DataFrame, tracked_games: pd.DataFrame) -> pd.DataFrame:
    """Computes one row of discount-behavior features per app_id from raw
    price_history events, for clustering. Games with fewer than
    MIN_DISCOUNT_EVENTS discount events are dropped (see MIN_DISCOUNT_EVENTS).

    price_history columns: app_id, date, price, discount_pct, source
    tracked_games columns: app_id, release_date, name, genre, publisher, ...
    """
    history = price_history.merge(
        tracked_games[["app_id", "release_date"]], on="app_id", how="inner"
    )
    history["date"] = pd.to_datetime(history["date"])
    history["release_date"] = pd.to_datetime(history["release_date"])
    history["days_since_release"] = (history["date"] - history["release_date"]).dt.days

    events = history[history["discount_pct"] > 0].copy()

    counts = events.groupby("app_id").size()
    eligible_ids = counts[counts >= MIN_DISCOUNT_EVENTS].index
    events = events[events["app_id"].isin(eligible_ids)]

    grouped = events.groupby("app_id")

    features = pd.DataFrame(
        {
            "avg_discount_depth": grouped["discount_pct"].mean(),
            "discount_depth_std": grouped["discount_pct"].std(),
            "num_discount_events": grouped.size(),
        }
    )

    first_discount_days = grouped["days_since_release"].min()
    features["time_to_first_discount_days"] = first_discount_days

    tracked_years = (grouped["days_since_release"].max() - first_discount_days) / 365.25
    # A game tracked for less than ~a month can't support a meaningful
    # per-year rate; floor the denominator to avoid absurd frequency spikes.
    tracked_years = tracked_years.clip(lower=30 / 365.25)
    features["discount_frequency_per_year"] = features["num_discount_events"] / tracked_years

    features["discount_depth_trend"] = grouped.apply(
        lambda g: _slope_per_year(g["days_since_release"], g["discount_pct"]),
        include_groups=False,
    )

    features = features.dropna(subset=FEATURE_COLUMNS)
    features = features.reset_index()
    return features.merge(tracked_games, on="app_id", how="left")

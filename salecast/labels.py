import numpy as np
import pandas as pd

from salecast.sale_calendar import days_until_next_sale_window

# Each (target_discount_pct, horizon_days) pair the smart-buy model answers
# "will this game hit target_discount_pct off within horizon_days" for.
SCENARIOS = [
    (50, 30),
    (30, 14),
    (70, 60),
]

# Spacing between synthetic "today" observation points sampled along each
# game's price timeline - dense enough to capture real discount cadence
# without generating a near-duplicate row for every single day.
OBSERVATION_STEP_DAYS = 7

# Placeholder for "no discount ever observed yet as of this point" - large
# enough that a model can learn it as a distinct "never" case rather than
# an unusually long-but-real gap; ever_discounted carries the same signal
# explicitly, so this value's exact magnitude doesn't matter much.
NEVER_DISCOUNTED_SENTINEL_DAYS = 9999

# Games with no cluster_labels row (not enough discount history to cluster -
# see salecast/features.py MIN_DISCOUNT_EVENTS) get their own category
# rather than being dropped.
UNCLUSTERED_SENTINEL = -1

FEATURE_COLUMNS = [
    "target_discount",
    "horizon_days",
    "days_since_release",
    "days_since_last_discount",
    "ever_discounted",
    "current_discount",
    "days_until_next_sale_window",
    "cluster_id",
    "review_score_pct",
]
CONTEXT_COLUMNS = ["genre", "publisher"]


def _current_discount_asof(
    event_dates: np.ndarray, event_discounts: np.ndarray, obs_dates: np.ndarray
) -> np.ndarray:
    """The discount_pct in effect at/before each obs date (0 if none yet)."""
    if len(event_dates) == 0:
        return np.zeros(len(obs_dates), dtype=int)
    idx = np.searchsorted(event_dates, obs_dates, side="right") - 1
    return np.where(idx >= 0, event_discounts[np.clip(idx, 0, None)], 0)


def _days_since_last_discount(
    discount_event_dates: np.ndarray, obs_dates: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """(days_since_last_discount, ever_discounted) as of each obs date, using
    only events where discount_pct > 0."""
    if len(discount_event_dates) == 0:
        never = np.full(len(obs_dates), NEVER_DISCOUNTED_SENTINEL_DAYS, dtype=float)
        return never, np.zeros(len(obs_dates), dtype=int)

    idx = np.searchsorted(discount_event_dates, obs_dates, side="right") - 1
    ever = idx >= 0
    last_dates = np.where(ever, discount_event_dates[np.clip(idx, 0, None)], obs_dates)
    days = (obs_dates - last_dates) / np.timedelta64(1, "D")
    days = np.where(ever, days, NEVER_DISCOUNTED_SENTINEL_DAYS)
    return days, ever.astype(int)


def _hits_target_within_horizon(
    event_dates: np.ndarray,
    event_discounts: np.ndarray,
    obs_dates: np.ndarray,
    horizon_days: int,
    target_discount: int,
) -> np.ndarray:
    """For each obs date, whether any event in [obs_date, obs_date+horizon]
    has discount_pct >= target_discount."""
    window_end = obs_dates + np.timedelta64(horizon_days, "D")
    lo = np.searchsorted(event_dates, obs_dates, side="left")
    hi = np.searchsorted(event_dates, window_end, side="right")
    labels = np.zeros(len(obs_dates), dtype=int)
    for i in range(len(obs_dates)):
        if hi[i] > lo[i]:
            labels[i] = int(event_discounts[lo[i]:hi[i]].max() >= target_discount)
    return labels


def _point_in_time_features(
    events: pd.DataFrame, obs_dates: np.ndarray, release_date: pd.Timestamp, cluster_id, review_score_pct
) -> pd.DataFrame:
    """events: one game's price_history rows (columns date [Timestamp],
    discount_pct), sorted by date. Everything computable as of each obs
    date, excluding the target-discount label itself."""
    event_dates = events["date"].values
    event_discounts = events["discount_pct"].fillna(0).values.astype(int)
    discount_event_dates = events.loc[events["discount_pct"] > 0, "date"].values

    current_discount = _current_discount_asof(event_dates, event_discounts, obs_dates)
    days_since_last_discount, ever_discounted = _days_since_last_discount(discount_event_dates, obs_dates)
    days_since_release = (obs_dates - np.datetime64(release_date)) / np.timedelta64(1, "D")
    days_until_sale = np.array(
        [days_until_next_sale_window(pd.Timestamp(d).date()) for d in obs_dates]
    )

    return pd.DataFrame(
        {
            "days_since_release": days_since_release,
            "days_since_last_discount": days_since_last_discount,
            "ever_discounted": ever_discounted,
            "current_discount": current_discount,
            "days_until_next_sale_window": days_until_sale,
            "cluster_id": cluster_id,
            "review_score_pct": review_score_pct,
        }
    )


def _prepare_history(price_history: pd.DataFrame) -> pd.DataFrame:
    history = price_history.copy()
    history["date"] = pd.to_datetime(history["date"])
    return history.sort_values(["app_id", "date"])


def _game_context(tracked_games: pd.DataFrame, cluster_labels: pd.DataFrame) -> pd.DataFrame:
    games = tracked_games.set_index("app_id")
    if cluster_labels.empty:
        games["cluster_id"] = UNCLUSTERED_SENTINEL
    else:
        clusters = cluster_labels.set_index("app_id")["cluster_id"]
        games = games.join(clusters, how="left")
        games["cluster_id"] = games["cluster_id"].fillna(UNCLUSTERED_SENTINEL).astype(int)
    return games


def build_training_examples(
    price_history: pd.DataFrame,
    tracked_games: pd.DataFrame,
    cluster_labels: pd.DataFrame,
    scenarios: list[tuple[int, int]] = SCENARIOS,
    observation_step_days: int = OBSERVATION_STEP_DAYS,
) -> pd.DataFrame:
    """One row per (game, observation date, scenario) with FEATURE_COLUMNS
    plus genre/publisher and a binary label: did a discount_pct >=
    target_discount occur within horizon_days of the observation date.
    Observation dates within horizon_days of a game's last known
    price_history date are excluded per-scenario, since we can't yet know
    whether they'd hit the target (the window isn't over)."""
    history = _prepare_history(price_history)
    games = _game_context(tracked_games, cluster_labels)

    rows = []
    for app_id, events in history.groupby("app_id"):
        if app_id not in games.index:
            continue
        game = games.loc[app_id]
        release_date = pd.to_datetime(game.get("release_date"))
        if pd.isna(release_date):
            continue

        event_dates = events["date"].values
        last_known_date = event_dates.max()
        if release_date > last_known_date:
            continue

        obs_dates = pd.date_range(release_date, last_known_date, freq=f"{observation_step_days}D").values
        if len(obs_dates) == 0:
            continue

        point_features = _point_in_time_features(
            events, obs_dates, release_date, game["cluster_id"], game.get("review_score_pct")
        )

        event_discounts = events["discount_pct"].fillna(0).values.astype(int)

        for target_discount, horizon_days in scenarios:
            max_obs_date = last_known_date - np.timedelta64(horizon_days, "D")
            usable = obs_dates <= max_obs_date
            if not usable.any():
                continue

            labels = _hits_target_within_horizon(
                event_dates, event_discounts, obs_dates[usable], horizon_days, target_discount
            )

            scenario_rows = point_features[usable].copy()
            scenario_rows["app_id"] = app_id
            scenario_rows["obs_date"] = obs_dates[usable]
            scenario_rows["target_discount"] = target_discount
            scenario_rows["horizon_days"] = horizon_days
            scenario_rows["genre"] = game.get("genre")
            scenario_rows["publisher"] = game.get("publisher")
            scenario_rows["label"] = labels
            rows.append(scenario_rows)

    columns = ["app_id", "obs_date"] + FEATURE_COLUMNS + CONTEXT_COLUMNS + ["label"]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.concat(rows, ignore_index=True)[columns]


def build_scoring_examples(
    price_history: pd.DataFrame,
    tracked_games: pd.DataFrame,
    cluster_labels: pd.DataFrame,
    scenarios: list[tuple[int, int]] = SCENARIOS,
    as_of: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """One row per (game, scenario) with FEATURE_COLUMNS as of as_of (default:
    the latest date anywhere in price_history), for every tracked game -
    including games with no price_history rows yet, whose features just
    reflect "no data observed" (current_discount=0, ever_discounted=0)."""
    history = _prepare_history(price_history)
    games = _game_context(tracked_games, cluster_labels)

    if as_of is None:
        as_of = history["date"].max() if len(history) else pd.Timestamp.today().normalize()
    obs_dates = np.array([np.datetime64(as_of)])

    empty_events = pd.DataFrame({"date": pd.Series(dtype="datetime64[ns]"), "discount_pct": pd.Series(dtype=float)})
    events_by_app = dict(iter(history.groupby("app_id")))

    rows = []
    for app_id, game in games.iterrows():
        release_date = pd.to_datetime(game.get("release_date"))
        if pd.isna(release_date):
            continue

        events = events_by_app.get(app_id, empty_events)
        point_features = _point_in_time_features(
            events, obs_dates, release_date, game["cluster_id"], game.get("review_score_pct")
        )

        for target_discount, horizon_days in scenarios:
            scenario_row = point_features.copy()
            scenario_row["app_id"] = app_id
            scenario_row["target_discount"] = target_discount
            scenario_row["horizon_days"] = horizon_days
            scenario_row["genre"] = game.get("genre")
            scenario_row["publisher"] = game.get("publisher")
            rows.append(scenario_row)

    columns = ["app_id"] + FEATURE_COLUMNS + CONTEXT_COLUMNS
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.concat(rows, ignore_index=True)[columns]

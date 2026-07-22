import numpy as np
import pandas as pd

from salecast.labels import (
    NEVER_DISCOUNTED_SENTINEL_DAYS,
    UNCLUSTERED_SENTINEL,
    _current_discount_asof,
    _days_since_last_discount,
    _hits_target_within_horizon,
    build_scoring_examples,
    build_training_examples,
)


def test_current_discount_asof_forward_fills():
    event_dates = np.array(["2020-01-01", "2020-03-01"], dtype="datetime64[ns]")
    event_discounts = np.array([0, 50])
    obs_dates = np.array(["2019-12-01", "2020-02-01", "2020-04-01"], dtype="datetime64[ns]")

    result = _current_discount_asof(event_dates, event_discounts, obs_dates)

    assert list(result) == [0, 0, 50]


def test_days_since_last_discount_tracks_only_positive_discount_events():
    discount_event_dates = np.array(["2020-03-01"], dtype="datetime64[ns]")
    obs_dates = np.array(["2020-02-01", "2020-03-15"], dtype="datetime64[ns]")

    days, ever = _days_since_last_discount(discount_event_dates, obs_dates)

    assert ever.tolist() == [0, 1]
    assert days[0] == NEVER_DISCOUNTED_SENTINEL_DAYS
    assert days[1] == 14


def test_days_since_last_discount_handles_no_discounts_ever():
    days, ever = _days_since_last_discount(
        np.array([], dtype="datetime64[ns]"), np.array(["2020-01-01"], dtype="datetime64[ns]")
    )

    assert ever.tolist() == [0]
    assert days[0] == NEVER_DISCOUNTED_SENTINEL_DAYS


def test_hits_target_within_horizon():
    event_dates = np.array(["2020-01-01", "2020-01-10", "2020-02-01"], dtype="datetime64[ns]")
    event_discounts = np.array([0, 30, 60])
    obs_dates = np.array(["2020-01-01"], dtype="datetime64[ns]")

    too_short = _hits_target_within_horizon(event_dates, event_discounts, obs_dates, 9, 50)
    long_enough = _hits_target_within_horizon(event_dates, event_discounts, obs_dates, 31, 50)

    assert too_short[0] == 0
    assert long_enough[0] == 1


def _fixture_data():
    tracked_games = pd.DataFrame(
        [
            {
                "app_id": 1, "name": "G1", "genre": "Action", "publisher": "Pub",
                "release_date": "2020-01-01", "review_count": 100, "review_score_pct": 90.0,
                "first_tracked_date": "2020-01-01",
            },
            {
                "app_id": 2, "name": "G2", "genre": "Indie", "publisher": "Pub2",
                "release_date": None, "review_count": 50, "review_score_pct": 80.0,
                "first_tracked_date": "2020-01-01",
            },
        ]
    )
    price_history = pd.DataFrame(
        [
            {"app_id": 1, "date": "2020-01-01", "price": 20.0, "discount_pct": 0, "source": "s"},
            {"app_id": 1, "date": "2020-01-15", "price": 20.0, "discount_pct": 0, "source": "s"},
            {"app_id": 1, "date": "2020-02-01", "price": 10.0, "discount_pct": 50, "source": "s"},
            {"app_id": 1, "date": "2020-02-15", "price": 20.0, "discount_pct": 0, "source": "s"},
            {"app_id": 1, "date": "2020-03-01", "price": 6.0, "discount_pct": 70, "source": "s"},
            {"app_id": 1, "date": "2020-03-15", "price": 20.0, "discount_pct": 0, "source": "s"},
        ]
    )
    cluster_labels = pd.DataFrame([{"app_id": 1, "cluster_id": 2}])
    return tracked_games, price_history, cluster_labels


def test_build_training_examples_excludes_games_missing_release_date():
    tracked_games, price_history, cluster_labels = _fixture_data()

    examples = build_training_examples(
        price_history, tracked_games, cluster_labels, scenarios=[(50, 30)], observation_step_days=14
    )

    assert set(examples["app_id"]) == {1}


def test_build_training_examples_assigns_cluster_id():
    tracked_games, price_history, cluster_labels = _fixture_data()

    examples = build_training_examples(
        price_history, tracked_games, cluster_labels, scenarios=[(50, 30)], observation_step_days=14
    )

    assert (examples["cluster_id"] == 2).all()


def test_build_training_examples_censors_observations_too_close_to_the_end():
    tracked_games, price_history, cluster_labels = _fixture_data()
    horizon_days = 30

    examples = build_training_examples(
        price_history, tracked_games, cluster_labels,
        scenarios=[(50, horizon_days)], observation_step_days=14,
    )

    last_known_date = pd.to_datetime(price_history["date"]).max()
    assert (examples["obs_date"] <= last_known_date - pd.Timedelta(days=horizon_days)).all()


def test_build_training_examples_has_expected_label_for_a_known_window():
    tracked_games, price_history, cluster_labels = _fixture_data()

    examples = build_training_examples(
        price_history, tracked_games, cluster_labels, scenarios=[(50, 30)], observation_step_days=14
    )

    # 2020-01-01 is 31 days before the 50%-off event on 2020-02-01, so a
    # 30-day horizon from this obs date should NOT capture it.
    row = examples[examples["obs_date"] == pd.Timestamp("2020-01-01")]
    assert row["label"].iloc[0] == 0

    # 2020-01-15 is within 30 days of the 2020-02-01 discount.
    row = examples[examples["obs_date"] == pd.Timestamp("2020-01-15")]
    assert row["label"].iloc[0] == 1


def test_build_scoring_examples_covers_every_game_and_scenario():
    tracked_games, price_history, cluster_labels = _fixture_data()
    tracked_games = tracked_games.copy()
    tracked_games.loc[tracked_games["app_id"] == 2, "release_date"] = "2021-01-01"

    scoring = build_scoring_examples(
        price_history, tracked_games, cluster_labels, scenarios=[(50, 30), (30, 14)]
    )

    assert set(scoring["app_id"]) == {1, 2}
    assert len(scoring) == 2 * 2  # 2 games x 2 scenarios


def test_build_scoring_examples_handles_game_with_no_price_history():
    tracked_games, price_history, cluster_labels = _fixture_data()
    tracked_games = tracked_games.copy()
    tracked_games.loc[tracked_games["app_id"] == 2, "release_date"] = "2021-01-01"

    scoring = build_scoring_examples(
        price_history, tracked_games, cluster_labels, scenarios=[(50, 30)]
    )

    row = scoring[scoring["app_id"] == 2].iloc[0]
    assert row["current_discount"] == 0
    assert row["ever_discounted"] == 0
    assert row["cluster_id"] == UNCLUSTERED_SENTINEL

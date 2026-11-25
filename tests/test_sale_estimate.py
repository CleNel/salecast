from datetime import date, timedelta

from salecast.sale_estimate import discount_start_dates, estimate_next_sale


def _starts(first: date, gaps: list[int]) -> list[date]:
    out = [first]
    for gap in gaps:
        out.append(out[-1] + timedelta(days=gap))
    return out


def test_discount_start_dates_finds_only_episode_starts():
    rows = [
        ("2026-01-01", 0),
        ("2026-01-05", 30),
        ("2026-01-06", 30),  # same episode continues
        ("2026-01-10", 0),
        ("2026-02-01", 50),
        ("2026-02-01", 40),  # duplicate date from another source
        ("2026-02-02", None),  # unknown, ignored
    ]
    assert discount_start_dates(rows) == [date(2026, 1, 5), date(2026, 2, 1)]


def test_discount_start_dates_counts_a_game_discounted_from_its_first_row():
    assert discount_start_dates([("2026-01-01", 20), ("2026-01-02", 0)]) == [date(2026, 1, 1)]


def test_returns_none_without_enough_history():
    starts = _starts(date(2026, 1, 1), [30, 30])  # 3 sales, below MIN_EPISODES
    assert estimate_next_sale(starts, as_of=date(2026, 4, 1)) is None


def test_range_is_conditioned_on_time_already_elapsed():
    # Gaps of 20/40/60/80/100 days; 30 days since last sale, so only the
    # 40+ day gaps are still possible: remaining waits of 10..70 days.
    starts = _starts(date(2025, 1, 1), [20, 40, 60, 80, 100])
    as_of = starts[-1] + timedelta(days=30)

    est = estimate_next_sale(starts, as_of=as_of)

    assert est["days_since_last_sale"] == 30
    assert not est["overdue"]
    assert 10 <= est["low_days"] < est["high_days"] <= 70
    assert est["earliest_date"] == (as_of + timedelta(days=est["low_days"])).isoformat()
    assert est["past_sales"] == 6


def test_overdue_game_gets_open_ended_low_bound():
    starts = _starts(date(2025, 1, 1), [20, 25, 30, 35])
    as_of = starts[-1] + timedelta(days=200)  # far longer than any past gap

    est = estimate_next_sale(starts, as_of=as_of)

    assert est["overdue"] is True
    assert est["low_days"] == 0
    assert est["high_days"] >= 1
    assert est["typical_gap_days"] == 28


def test_includes_seasonal_sale_context():
    starts = _starts(date(2025, 1, 1), [30, 30, 30, 30])
    est = estimate_next_sale(starts, as_of=date(2025, 6, 1))
    assert est["days_until_seasonal_sale"] == 25  # Summer Sale starts Jun 26

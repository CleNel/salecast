"""Rough "when will this game next go on sale" range, from the game's own
discount history.

Deliberately a range, not a date. Backtested on real snapshot data, a
per-game predicted date was off by ~3 weeks on average and no better than
guessing the same number of days for every game, but a 10th-90th percentile
range of the game's own past gaps contained the real next-sale date roughly
3 times in 4. So that's what we show - see documentation/ml.md.
"""
from datetime import date, timedelta

import numpy as np

from salecast.sale_calendar import days_until_next_sale_window

# Need at least this many past discount starts (so MIN_EPISODES - 1 gaps) to
# say anything about a game's rhythm.
MIN_EPISODES = 4
LOW_QUANTILE = 0.10
HIGH_QUANTILE = 0.90
# After conditioning on "hasn't gone on sale yet", need this many comparable
# past gaps left; otherwise the game is overdue by its own standards.
MIN_REMAINING_GAPS = 2


def discount_start_dates(rows) -> list[date]:
    """Dates a discount began: a day with discount_pct > 0 where the previous
    recorded day had none. rows are (date_iso, discount_pct) pairs; several
    rows on one date (different sources) collapse to the deepest discount."""
    by_date: dict[str, int] = {}
    for day, pct in rows:
        if pct is None:
            continue
        by_date[day] = max(by_date.get(day, 0), pct)

    starts = []
    previous = 0
    for day in sorted(by_date):
        pct = by_date[day]
        if pct > 0 and previous == 0:
            starts.append(date.fromisoformat(day))
        previous = pct
    return starts


def estimate_next_sale(starts: list[date], as_of: date | None = None) -> dict | None:
    """Range of days from as_of until the game's next discount, or None if
    there isn't enough history. Caller should skip this for games already on
    sale. Always includes the next seasonal sale window as context."""
    as_of = as_of or date.today()
    if len(starts) < MIN_EPISODES:
        return None

    starts = sorted(starts)
    gaps = np.array([(b - a).days for a, b in zip(starts, starts[1:])], dtype=float)
    elapsed = (as_of - starts[-1]).days

    # Condition on the game not having gone on sale yet: only gaps longer
    # than what's already elapsed are still "possible", and what remains of
    # them is the wait.
    remaining = gaps[gaps > elapsed] - elapsed
    overdue = len(remaining) < MIN_REMAINING_GAPS
    if overdue:
        low, high = 0.0, float(np.quantile(gaps, HIGH_QUANTILE))
    else:
        low = float(np.quantile(remaining, LOW_QUANTILE))
        high = float(np.quantile(remaining, HIGH_QUANTILE))

    low_days, high_days = int(round(low)), max(int(round(high)), 1)
    return {
        "low_days": low_days,
        "high_days": high_days,
        "earliest_date": (as_of + timedelta(days=low_days)).isoformat(),
        "latest_date": (as_of + timedelta(days=high_days)).isoformat(),
        "days_since_last_sale": elapsed,
        "typical_gap_days": int(round(float(np.median(gaps)))),
        "past_sales": len(starts),
        "overdue": overdue,
        "days_until_seasonal_sale": days_until_next_sale_window(as_of),
    }

"""Rough "when will this game next go on sale" range, from the game's own
discount history.

Deliberately a range, not a date. Backtested on live D1 data (Nov 2026), a
per-game predicted date was off by ~16 days on average, no better than
guessing the same number of days for every game, but a 10th-90th percentile
range of the game's own past gaps contained the real next-sale date about
88% of the time (games with 7+ past sales). So that's what we show - see
documentation/ml.md.
"""
from datetime import date, timedelta

import numpy as np

from salecast.sale_calendar import days_until_next_sale_window

# Need at least this many past discount starts (so MIN_EPISODES - 1 gaps) to
# say anything about a game's rhythm. Backtest: with 4-6 past sales the range
# only held 57% of the time, with 7+ it held 81-89%.
MIN_EPISODES = 7

# Confidence is how tight the range is, from the Nov 2026 backtest (5,308
# evaluations, games with 7+ past sales). Width in days -> label, plus the
# share of backtest cases where the real next-sale date fell inside a range
# of that width (rounded down). Narrow ranges are the most useful but hit a
# little less often, so the hit rate is shown alongside the label.
CONFIDENCE_TIERS = [
    (45, "high", 80),     # 82% measured
    (80, "medium", 90),   # 90% measured
    (None, "low", 90),    # 91% measured
]
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


def _confidence(width_days: int, overdue: bool) -> tuple[str, int | None]:
    """(label, backtested hit rate %) for a range of this width. Overdue games
    are always low confidence and have no measured hit rate - the backtest
    had too few of them (42) to quote a number."""
    if overdue:
        return "low", None
    for max_width, label, hit_rate in CONFIDENCE_TIERS:
        if max_width is None or width_days <= max_width:
            return label, hit_rate
    return "low", None


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
    confidence, hit_rate_pct = _confidence(high_days - low_days, overdue)
    return {
        "confidence": confidence,
        "hit_rate_pct": hit_rate_pct,
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

from datetime import date, timedelta

# Approximate recurring Steam seasonal sale windows: (start_month, start_day,
# duration_days). Valve doesn't publish future dates, but each sale reliably
# lands within a few days of the same week every year.
SALE_WINDOWS = [
    (1, 20, 17),   # Lunar New Year Sale
    (3, 14, 8),    # Spring Sale
    (6, 26, 15),   # Summer Sale
    (11, 26, 8),   # Autumn Sale
    (12, 19, 15),  # Winter Sale (spills into January)
]


def days_until_next_sale_window(as_of: date) -> int:
    """Days from as_of until the next known Steam seasonal sale window
    starts, or 0 if as_of already falls within one."""
    next_start = None
    for month, day, duration in SALE_WINDOWS:
        for year in (as_of.year - 1, as_of.year, as_of.year + 1):
            start = date(year, month, day)
            end = start + timedelta(days=duration - 1)
            if start <= as_of <= end:
                return 0
            if start > as_of and (next_start is None or start < next_start):
                next_start = start
    return (next_start - as_of).days

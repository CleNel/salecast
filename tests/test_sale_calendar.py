from datetime import date

from salecast.sale_calendar import days_until_next_sale_window


def test_returns_zero_inside_winter_sale():
    assert days_until_next_sale_window(date(2026, 12, 25)) == 0


def test_returns_zero_inside_summer_sale():
    assert days_until_next_sale_window(date(2026, 7, 1)) == 0


def test_returns_days_until_next_window():
    assert days_until_next_sale_window(date(2026, 12, 5)) == 14


def test_handles_year_boundary_between_winter_and_lunar_new_year():
    assert days_until_next_sale_window(date(2026, 1, 5)) == 15


def test_returns_zero_on_first_day_of_a_window():
    assert days_until_next_sale_window(date(2026, 1, 20)) == 0

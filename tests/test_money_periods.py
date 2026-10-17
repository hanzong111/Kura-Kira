from datetime import date

import pytest

from duit.money import fmt, parse_amount, split_even, split_ratio
from duit.periods import week_in_month, weekly_allowance

WEEKDAYS, WEEKEND = (0, 1, 2, 3, 4), (5, 6)


@pytest.mark.parametrize("text,sen", [
    ("RM13.20", 1320), ("13.2", 1320), ("rm 56", 5600), ("56.50", 5650), ("RM1,250.00", 125000),
    (".5", 50), (56.5, 5650), (12, 1200), ("14.50 ", 1450), ("26.20rm", 2620),
])
def test_parse_amount(text, sen):
    assert parse_amount(text) == sen


@pytest.mark.parametrize("bad", ["", "abc", "12.345", "RM", "1.2.3", True])
def test_parse_amount_rejects(bad):
    with pytest.raises(ValueError):
        parse_amount(bad)


def test_fmt():
    assert fmt(5650) == "RM56.50"
    assert fmt(125000) == "RM1,250.00"
    assert fmt(-1450) == "-RM14.50"


def test_splits_add_up_exactly():
    assert split_even(1001, 2) == [501, 500]
    assert split_ratio(6000, [2, 1]) == [4000, 2000]
    assert sum(split_ratio(1000, [1, 1, 1])) == 1000


def test_october_2026_weeks():
    # Oct 2026: Thu 1st .. Sat 31st -> 22 weekdays, 9 weekend days
    first = week_in_month(date(2026, 10, 1), "2026-10", WEEKEND)
    assert (first.bucket_days, first.days_left) == (2, 9)      # Sat 3 + Sun 4
    last = week_in_month(date(2026, 10, 31), "2026-10", WEEKEND)
    assert (last.bucket_days, last.days_left) == (1, 1)        # lone Saturday
    wd = week_in_month(date(2026, 10, 1), "2026-10", WEEKDAYS)
    assert (wd.bucket_days, wd.days_left, wd.days_elapsed) == (2, 22, 1)


def test_weekly_allowance_never_exceeds_month():
    cap = 80000  # RM800 weekend
    w1 = week_in_month(date(2026, 10, 3), "2026-10", WEEKEND)
    assert weekly_allowance(cap, 0, w1) == 80000 * 2 // 9      # RM177.77 for a full weekend
    # underspend carries forward: nothing spent in the first 4 weekends -> last Saturday gets it all
    w5 = week_in_month(date(2026, 10, 31), "2026-10", WEEKEND)
    assert weekly_allowance(cap, 0, w5) == cap
    # overspent month -> nothing left
    assert weekly_allowance(cap, 90000, w5) == 0

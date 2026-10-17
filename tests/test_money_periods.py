from datetime import date

import pytest

from duit.money import fmt, parse_amount, split_even, split_ratio
from duit.periods import month_weeks, week_of

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


def test_october_2026_weekly_targets():
    # Oct 2026: Thu 1st .. Sat 31st
    wd = month_weeks("2026-10", WEEKDAYS, 2000)
    assert [(w.days, w.target) for w in wd] == [(2, 4000), (5, 10000), (5, 10000), (5, 10000), (5, 10000)]
    we = month_weeks("2026-10", WEEKEND, 10000)
    assert [(w.days, w.target) for w in we] == [(2, 20000), (2, 20000), (2, 20000), (2, 20000), (1, 10000)]
    assert sum(w.target for w in wd) == 44000 and sum(w.target for w in we) == 90000


def test_tracking_start_drops_earlier_days():
    wd = month_weeks("2026-10", WEEKDAYS, 2000, date(2026, 10, 18))  # starts on a Sunday
    assert [w.target for w in wd] == [0, 0, 0, 10000, 10000]
    we = month_weeks("2026-10", WEEKEND, 10000, date(2026, 10, 18))
    assert [w.target for w in we] == [0, 0, 10000, 20000, 10000]   # Sun 18 = half a weekend


def test_week_of():
    we = month_weeks("2026-10", WEEKEND, 10000)
    assert week_of(we, date(2026, 10, 17)) == 2
    assert week_of(we, date(2026, 11, 1)) == 4   # Sunday after the month: same Mon-Sun week

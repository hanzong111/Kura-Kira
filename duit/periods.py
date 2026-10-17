"""Calendar maths: months, Mon-Sun weeks, and the weekly-bucket allowance."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_bounds(month: str) -> tuple[date, date]:
    y, m = map(int, month.split("-"))
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def prev_month(month: str) -> str:
    first, _ = month_bounds(month)
    return month_key(first - timedelta(days=1))


def week_bounds(d: date) -> tuple[date, date]:
    start = d - timedelta(days=d.weekday())
    return start, start + timedelta(days=6)


def days_between(a: date, b: date):
    """Inclusive."""
    for i in range((b - a).days + 1):
        yield a + timedelta(days=i)


def count_days(a: date, b: date, weekdays: tuple[int, ...]) -> int:
    return sum(1 for d in days_between(a, b) if d.weekday() in weekdays)


@dataclass(frozen=True)
class Week:
    start: date            # Monday (may be in the previous month)
    end: date              # Sunday (may be in the next month)
    in_month_start: date   # clipped to the month
    in_month_end: date
    bucket_days: int       # days of this bucket inside the clipped week
    days_left: int         # bucket days from this week's start to month end
    days_elapsed: int      # bucket days in this week up to and including `today`


def week_in_month(today: date, month: str, weekdays: tuple[int, ...]) -> Week:
    first, last = month_bounds(month)
    ws, we = week_bounds(today)
    a, b = max(ws, first), min(we, last)
    return Week(
        start=ws, end=we, in_month_start=a, in_month_end=b,
        bucket_days=count_days(a, b, weekdays),
        days_left=count_days(a, last, weekdays),
        days_elapsed=count_days(a, min(today, b), weekdays),
    )


def weekly_allowance(cap_sen: int, spent_before_week_sen: int, week: Week) -> int:
    """This week's share of what's left of the month.

    Underspend carries forward and overspend shrinks later weeks, so the month never
    goes over the plan. Partial weeks at the month edges get a share proportional to
    their bucket days (a lone Saturday gets half of a full weekend).
    """
    if week.bucket_days == 0 or week.days_left == 0:
        return 0
    left = max(cap_sen - spent_before_week_sen, 0)
    return left * week.bucket_days // week.days_left

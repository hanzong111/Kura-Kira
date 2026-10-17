"""Calendar maths: months, Mon-Sun weeks, and the weekly targets with carry-over."""

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
    start: date      # Monday (may be in the previous month)
    end: date        # Sunday (may be in the next month)
    a: date          # first counted day: clipped to the month and the tracking start
    b: date          # last counted day: clipped to the month
    days: int        # bucket days counted in this week
    target: int      # sen: daily budget x counted days


def month_weeks(month: str, weekdays: tuple[int, ...], per_day_sen: int, start: date | None = None) -> list[Week]:
    """The month's Mon-Sun weeks for a weekly bucket, each with its target = daily budget x counted days.

    RM20/weekday -> a full week RM100, Thu-Fri RM40; RM100/weekend day -> RM200, a lone Saturday RM100.
    Days outside the month (or before `start`) aren't counted.
    """
    first, last = month_bounds(month)
    begin = max(first, start) if start else first
    out = []
    monday = week_bounds(first)[0]
    while monday <= last:
        sunday = monday + timedelta(days=6)
        a, b = max(monday, begin), min(sunday, last)
        days = count_days(a, b, weekdays) if a <= b else 0
        out.append(Week(monday, sunday, a, b, days, per_day_sen * days))
        monday += timedelta(days=7)
    return out


def week_of(weeks: list[Week], d: date) -> int | None:
    return next((i for i, w in enumerate(weeks) if w.start <= d <= w.end), None)

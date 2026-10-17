"""Placeholder spends for days before tracking began: exactly on budget (daily amount x days).

`python -m duit backfill 2026-10-01 2026-10-16` adds, per person and per Mon-Sun week, one weekday entry
and one weekend entry worth the daily budget x the days covered, dated the last such day. They show up
in the dashboard like any spend ("Before tracking"), so carry-over starts at zero. Safe to re-run: each
placeholder has a fixed message id.
"""

from __future__ import annotations

from datetime import date

from .ledger import Ledger
from .periods import days_between, month_key, week_bounds
from .report import plan_amount

PLACE = "Before tracking"
NOTE = "placeholder: on budget for days before tracking began"


def backfill(led: Ledger, first: date, last: date) -> list[dict]:
    cfg = led.cfg
    added = []
    weekly = [b for b in cfg.buckets.values() if b.kind == "weekly"]
    for person in cfg.people:
        for b in weekly:
            # group the bucket's days by Mon-Sun week (and month, so each chunk uses its month's plan)
            chunks: dict[tuple, list[date]] = {}
            for d in days_between(first, last):
                if d.weekday() in b.days:
                    chunks.setdefault((week_bounds(d)[0], month_key(d)), []).append(d)
            for (_, month), days in sorted(chunks.items()):
                led.ensure_month(month)
                per_day = plan_amount(led.conn, month, person, b.key)
                sen = per_day * len(days)
                if sen <= 0:
                    continue
                e = led.log_spend(sender=person, place=PLACE, item=f"{len(days)} day{'s' if len(days) > 1 else ''}",
                                  total=f"{sen // 100}.{sen % 100:02d}", bucket=b.key, category="Other",
                                  paid_by=person, spent_on=days[-1], raw_text=NOTE, chat_id="backfill",
                                  msg_id=f"{person}:{b.key}:{days[0].isoformat()}")
                added.append({"id": e["id"], "person": person, "bucket": b.key, "from": days[0].isoformat(),
                              "to": days[-1].isoformat(), "amount": sen, "duplicate": e["duplicate"]})
    return added

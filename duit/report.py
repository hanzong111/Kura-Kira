"""Read side: budget status, pace, balances. All numbers come from the ledger, never the LLM."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from .config import Config
from .periods import month_bounds, week_in_month, weekly_allowance

ON_TRACK, AHEAD, OVER = "ok", "ahead", "over"
PACE_SLACK = 0.05  # a few percent ahead of the calendar still counts as on track


def pace_status(spent: int, cap: int, elapsed: float) -> str:
    if spent > cap:
        return OVER
    if cap == 0:
        return ON_TRACK
    return AHEAD if spent / cap > elapsed + PACE_SLACK else ON_TRACK


def month_elapsed(month: str, today: date) -> float:
    first, last = month_bounds(month)
    if today < first:
        return 0.0
    if today > last:
        return 1.0
    return today.day / last.day


def spent(conn: sqlite3.Connection, person: str, bucket: str | None, start: date, end: date) -> int:
    """Sum of `person`'s shares in `bucket` (None = Unsorted) spent between start and end inclusive."""
    bucket_sql = "e.bucket IS NULL" if bucket is None else "e.bucket = :bucket"
    row = conn.execute(
        f"""SELECT COALESCE(SUM(s.amount_sen), 0) FROM shares s JOIN entries e ON e.id = s.entry_id
            WHERE e.deleted_at IS NULL AND s.person = :person AND {bucket_sql}
              AND e.spent_on BETWEEN :start AND :end""",
        {"person": person, "bucket": bucket, "start": start.isoformat(), "end": end.isoformat()},
    ).fetchone()
    return row[0]


def plan_amount(conn: sqlite3.Connection, month: str, person: str, bucket: str) -> int:
    row = conn.execute("SELECT amount_sen FROM plans WHERE month=? AND person=? AND bucket=?",
                       (month, person, bucket)).fetchone()
    return row[0] if row else 0


def bucket_status(conn: sqlite3.Connection, cfg: Config, month: str, person: str, bucket_key: str,
                  today: date) -> dict:
    b = cfg.buckets[bucket_key]
    first, last = month_bounds(month)
    cap = plan_amount(conn, month, person, bucket_key)

    if b.kind == "fixed":
        row = conn.execute("SELECT paid_at, auto FROM fixed_payments WHERE month=? AND person=? AND bucket=?",
                           (month, person, bucket_key)).fetchone()
        paid = bool(row and row["paid_at"])
        return {"bucket": bucket_key, "label": b.label, "kind": b.kind, "amount": cap,
                "paid": paid, "auto": bool(row and row["auto"]), "status": "paid" if paid else "due"}

    used = spent(conn, person, bucket_key, first, last)
    out = {"bucket": bucket_key, "label": b.label, "kind": b.kind, "cap": cap, "spent": used,
           "left": cap - used, "pct": round(used / cap, 4) if cap else (0.0 if used == 0 else None),
           "status": pace_status(used, cap, month_elapsed(month, today))}

    if b.kind == "weekly" and first <= today <= last:
        wk = week_in_month(today, month, b.days)
        before = spent(conn, person, bucket_key, first, wk.in_month_start - timedelta(days=1))
        allowance = weekly_allowance(cap, before, wk)
        this_week = spent(conn, person, bucket_key, wk.in_month_start, wk.in_month_end)
        elapsed = wk.days_elapsed / wk.bucket_days if wk.bucket_days else 1.0
        out["week"] = {"start": wk.start.isoformat(), "end": wk.end.isoformat(),
                       "in_month_start": wk.in_month_start.isoformat(), "in_month_end": wk.in_month_end.isoformat(),
                       "allowance": allowance, "spent": this_week, "left": allowance - this_week,
                       "days": wk.bucket_days, "days_elapsed": wk.days_elapsed,
                       "status": pace_status(this_week, allowance, elapsed)}
    return out


def balance(conn: sqlite3.Connection, cfg: Config) -> dict:
    """Net position per person: positive = is owed money, negative = owes. Sums to zero."""
    net = {p: 0 for p in cfg.people}
    for e in conn.execute("SELECT id, total_sen, paid_by FROM entries WHERE deleted_at IS NULL AND paid_by IS NOT NULL"):
        if e["paid_by"] == "each":
            continue  # everyone covered their own share
        net[e["paid_by"]] += e["total_sen"]
        for s in conn.execute("SELECT person, amount_sen FROM shares WHERE entry_id=?", (e["id"],)):
            net[s["person"]] -= s["amount_sen"]
    for s in conn.execute("SELECT from_person, to_person, amount_sen FROM settlements WHERE deleted_at IS NULL"):
        net[s["from_person"]] += s["amount_sen"]
        net[s["to_person"]] -= s["amount_sen"]
    owes = None
    debtors = [p for p, v in net.items() if v < 0]
    creditors = [p for p, v in net.items() if v > 0]
    if len(debtors) == 1 and len(creditors) == 1:
        owes = {"from": debtors[0], "to": creditors[0], "amount": net[creditors[0]]}
    return {"net": net, "owes": owes}


def paid_totals(conn: sqlite3.Connection, cfg: Config, month: str) -> dict:
    """What each person actually paid out this month (spends + fixed bills), and what's unknown."""
    first, last = month_bounds(month)
    rng = (first.isoformat(), last.isoformat())
    out = {p: {"spends": 0, "fixed": 0} for p in cfg.people}
    unknown = 0
    for e in conn.execute("SELECT id, total_sen, paid_by FROM entries WHERE deleted_at IS NULL "
                          "AND spent_on BETWEEN ? AND ?", rng):
        if e["paid_by"] is None:
            unknown += e["total_sen"]
        elif e["paid_by"] == "each":
            for s in conn.execute("SELECT person, amount_sen FROM shares WHERE entry_id=?", (e["id"],)):
                out[s["person"]]["spends"] += s["amount_sen"]
        else:
            out[e["paid_by"]]["spends"] += e["total_sen"]
    for f in conn.execute("SELECT person, amount_sen FROM fixed_payments WHERE month=? AND paid_at IS NOT NULL",
                          (month,)):
        out[f["person"]]["fixed"] += f["amount_sen"]
    for v in out.values():
        v["total"] = v["spends"] + v["fixed"]
    return {"people": out, "unknown": unknown}


def pending(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT * FROM entries WHERE deleted_at IS NULL AND (bucket IS NULL OR paid_by IS NULL)
           ORDER BY id""").fetchall()
    out = []
    for r in rows:
        needs = [n for n, missing in (("bucket", r["bucket"] is None), ("payer", r["paid_by"] is None)) if missing]
        out.append({"id": r["id"], "place": r["place"], "total": r["total_sen"], "sender": r["sender"],
                    "spent_on": r["spent_on"], "needs": needs, "question_msg_id": r["question_msg_id"]})
    return out


def status(conn: sqlite3.Connection, cfg: Config, month: str, today: date) -> dict:
    """Everything the dashboard and `how are we doing?` need, for one month."""
    first, last = month_bounds(month)
    people = {}
    for p in cfg.people:
        buckets = {k: bucket_status(conn, cfg, month, p, k, today) for k in cfg.buckets}
        goals = [b for b in buckets.values() if b["kind"] != "fixed"]
        fixed = [b for b in buckets.values() if b["kind"] == "fixed"]
        unsorted = spent(conn, p, None, first, last)
        goal_cap = sum(b["cap"] for b in goals)
        goal_spent = sum(b["spent"] for b in goals)
        people[p] = {
            "name": cfg.people[p].name,
            "buckets": buckets,
            "goals": {"cap": goal_cap, "spent": goal_spent, "left": goal_cap - goal_spent,
                      "status": pace_status(goal_spent, goal_cap, month_elapsed(month, today))},
            "unsorted": unsorted,
            "fixed": {"total": sum(b["amount"] for b in fixed),
                      "paid": sum(1 for b in fixed if b["paid"]), "count": len(fixed)},
            "outflow_plan": goal_cap + sum(b["amount"] for b in fixed),
        }

    combined_buckets = {}
    for k, b in cfg.buckets.items():
        rows = [people[p]["buckets"][k] for p in people]
        if b.kind == "fixed":
            combined_buckets[k] = {"bucket": k, "label": b.label, "kind": b.kind,
                                   "amount": sum(r["amount"] for r in rows),
                                   "paid": sum(1 for r in rows if r["paid"]), "count": len(rows)}
        else:
            cap, used = sum(r["cap"] for r in rows), sum(r["spent"] for r in rows)
            combined_buckets[k] = {"bucket": k, "label": b.label, "kind": b.kind, "cap": cap, "spent": used,
                                   "left": cap - used,
                                   "status": pace_status(used, cap, month_elapsed(month, today))}
    gcap = sum(people[p]["goals"]["cap"] for p in people)
    gspent = sum(people[p]["goals"]["spent"] for p in people)
    return {
        "month": month,
        "today": today.isoformat(),
        "elapsed": round(month_elapsed(month, today), 4),
        "currency": cfg.currency,
        "people": people,
        "combined": {
            "buckets": combined_buckets,
            "goals": {"cap": gcap, "spent": gspent, "left": gcap - gspent,
                      "status": pace_status(gspent, gcap, month_elapsed(month, today))},
            "unsorted": sum(people[p]["unsorted"] for p in people),
            "fixed": {"paid": sum(people[p]["fixed"]["paid"] for p in people),
                      "count": sum(people[p]["fixed"]["count"] for p in people)},
            "outflow_plan": sum(people[p]["outflow_plan"] for p in people),
        },
        "paid": paid_totals(conn, cfg, month),
        "balance": balance(conn, cfg),
        "pending": pending(conn),
    }

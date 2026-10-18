"""Read side: budget status, pace, balances. All numbers come from the ledger, never the LLM."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from .config import Config
from .periods import count_days, month_bounds, month_weeks, week_of

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


def installment(conn: sqlite3.Connection, b, person: str) -> dict:
    """Progress of an installment over all its months: how many paid, how much of the total."""
    rows = {r["month"]: r for r in conn.execute(
        "SELECT month, amount_sen, paid_at FROM fixed_payments WHERE person=? AND bucket=?", (person, b.key))}
    amounts = {m: rows[m]["amount_sen"] if m in rows else b.amount_sen for m in b.months}
    done = [m for m in b.months if m in rows and rows[m]["paid_at"]]
    total, paid = sum(amounts.values()), sum(amounts[m] for m in done)
    return {"months": list(b.months), "paid_months": done, "count": len(b.months), "done": len(done),
            "total": total, "spent": paid, "left": total - paid}


def bucket_status(conn: sqlite3.Connection, cfg: Config, month: str, person: str, bucket_key: str,
                  today: date) -> dict:
    b = cfg.buckets[bucket_key]
    first, last = month_bounds(month)
    cap = plan_amount(conn, month, person, bucket_key)

    if b.kind == "fixed":
        row = conn.execute("SELECT paid_at, auto FROM fixed_payments WHERE month=? AND person=? AND bucket=?",
                           (month, person, bucket_key)).fetchone()
        paid = bool(row and row["paid_at"])
        out = {"bucket": bucket_key, "label": b.label, "kind": b.kind, "amount": cap,
               "paid": paid, "auto": bool(row and row["auto"]), "status": "paid" if paid else "due"}
        if b.months:
            out["installment"] = installment(conn, b, person)
        return out

    if b.kind == "weekly":
        return _weekly_status(conn, cfg, month, person, b, cap, today)

    used = spent(conn, person, bucket_key, first, last)
    return {"bucket": bucket_key, "label": b.label, "kind": b.kind, "cap": cap, "spent": used,
            "left": cap - used, "pct": round(used / cap, 4) if cap else (0.0 if used == 0 else None),
            "status": pace_status(used, cap, month_elapsed(month, today))}


def _weekly_status(conn: sqlite3.Connection, cfg: Config, month: str, person: str, b, per_day: int,
                   today: date) -> dict:
    """Weekday/weekend: each week has a fixed target; what's under/over in earlier weeks of the month
    carries into this week ("can spend" = target + carry-over, never below 0). Resets every month.

    Days before `tracking_start` either don't exist for budgeting (`before_start = "ignore"`: partial
    targets from the start date) or count as exactly on budget (`"maxed"`: full targets, the pre-start
    share assumed spent, no carry-over from them). Spends logged for pre-start days are not counted.
    """
    first, last = month_bounds(month)
    start = cfg.tracking_start if cfg.tracking_start and cfg.tracking_start > first else None
    maxed = start is not None and cfg.before_start == "maxed"
    weeks = month_weeks(month, b.days, per_day, None if maxed else start)
    begin = max(first, start) if start else first

    def actual(a: date, z: date) -> int:
        a = max(a, begin)
        return spent(conn, person, b.key, a, z) if a <= z else 0

    def assumed(w) -> int:
        if not maxed or not w.days:
            return 0
        pre = count_days(w.a, min(w.b, start - timedelta(days=1)), b.days) if w.a < start else 0
        return per_day * pre

    counted = [w for w in weeks if w.days]
    cap = sum(w.target for w in counted)
    pre_total = sum(assumed(w) for w in counted)
    used = actual(first, last) + pre_total
    # elapsed share of the month's target, by bucket days (so a weekend bar isn't "ahead" on a Monday)
    m0 = counted[0].a if counted else first
    total_days = sum(w.days for w in counted)
    done_days = count_days(m0, min(today, last), b.days) if today >= m0 else 0
    elapsed = (done_days / total_days if total_days else 1.0) if today <= last else 1.0
    out = {"bucket": b.key, "label": b.label, "kind": b.kind, "per_day": per_day, "target": per_day * len(b.days),
           "cap": cap, "spent": used,
           "assumed": pre_total, "left": cap - used,
           "pct": round(used / cap, 4) if cap else (0.0 if used == 0 else None),
           "status": pace_status(used, cap, elapsed)}

    i = week_of(weeks, today) if first <= today <= last else None
    if i is not None and weeks[i].days:
        w = weeks[i]
        carry = sum(x.target - assumed(x) - actual(x.a, x.b) for x in weeks[:i] if x.days)
        can_spend = max(w.target + carry, 0)
        this_week = assumed(w) + actual(w.a, w.b)
        days_elapsed = count_days(w.a, min(today, w.b), b.days)
        out["week"] = {"start": w.start.isoformat(), "end": w.end.isoformat(), "per_day": per_day,
                       "in_month_start": w.a.isoformat(), "in_month_end": w.b.isoformat(),
                       "target": w.target, "carry": carry, "allowance": can_spend,
                       "spent": this_week, "assumed": assumed(w), "left": can_spend - this_week,
                       "days": w.days, "days_elapsed": days_elapsed,
                       "status": pace_status(this_week, can_spend, days_elapsed / w.days)}
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
    """What each person actually paid out this month (spends + fixed bills), and what's unknown.
    `rows` breaks it down by bucket (config order, "unsorted" last): who paid for what. `transfers` is money
    handed from one to the other this month (settle-ups, advances): it moves the balance, never a budget."""
    first, last = month_bounds(month)
    rng = (first.isoformat(), last.isoformat())
    out = {p: {"spends": 0, "fixed": 0} for p in cfg.people}
    by: dict[str, dict[str, int]] = {}
    unknown = 0

    def add(person: str, bucket: str | None, sen: int, kind: str) -> None:
        out[person][kind] += sen
        row = by.setdefault(bucket or "unsorted", dict.fromkeys(cfg.people, 0))
        row[person] += sen

    for e in conn.execute("SELECT id, total_sen, paid_by, bucket FROM entries WHERE deleted_at IS NULL "
                          "AND spent_on BETWEEN ? AND ?", rng):
        if e["paid_by"] is None:
            unknown += e["total_sen"]
        elif e["paid_by"] == "each":
            for s in conn.execute("SELECT person, amount_sen FROM shares WHERE entry_id=?", (e["id"],)):
                add(s["person"], e["bucket"], s["amount_sen"], "spends")
        else:
            add(e["paid_by"], e["bucket"], e["total_sen"], "spends")
    for f in conn.execute("SELECT person, bucket, amount_sen FROM fixed_payments WHERE month=? AND paid_at IS NOT NULL",
                          (month,)):
        add(f["person"], f["bucket"], f["amount_sen"], "fixed")
    for v in out.values():
        v["total"] = v["spends"] + v["fixed"]
    order = [*cfg.buckets, "unsorted"]
    rows = [{"bucket": k, "people": {p: {"amount": by[k][p]} for p in cfg.people},
             "total": sum(by[k].values())} for k in order if k in by]
    transfers = [{"on": s["settled_on"], "from": s["from_person"], "to": s["to_person"], "amount": s["amount_sen"],
                  "note": s["raw_text"] or ""}
                 for s in conn.execute("SELECT * FROM settlements WHERE deleted_at IS NULL AND settled_on BETWEEN ? AND ? "
                                       "ORDER BY settled_on, id", rng)]
    return {"people": out, "unknown": unknown, "rows": rows, "transfers": transfers}


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


def totals(var_cap: int, var_spent: int, fixed_cap: int, fixed_paid: int, elapsed: float) -> dict:
    """The month's whole plan: spending targets + fixed bills (house, car, parents, installments).
    spent = spending + bills paid. Status judges only the spending (bills can't overspend), and the pace mark
    sits where you'd be with every bill paid plus spending on the calendar's pace."""
    cap, used = var_cap + fixed_cap, var_spent + fixed_paid
    st = OVER if var_spent > var_cap else pace_status(var_spent, var_cap, elapsed)
    return {"cap": cap, "spent": used, "left": cap - used, "status": st,
            "pace": round((fixed_cap + var_cap * elapsed) / cap, 4) if cap else elapsed,
            "variable_cap": var_cap, "variable_spent": var_spent, "fixed": fixed_cap, "fixed_paid": fixed_paid}


def status(conn: sqlite3.Connection, cfg: Config, month: str, today: date) -> dict:
    """Everything the dashboard and `how are we doing?` need, for one month."""
    first, last = month_bounds(month)
    people = {}
    for p in cfg.people:
        buckets = {k: bucket_status(conn, cfg, month, p, k, today) for k in cfg.buckets_in(month)}
        goals = [b for b in buckets.values() if b["kind"] != "fixed"]
        fixed = [b for b in buckets.values() if b["kind"] == "fixed"]
        unsorted = spent(conn, p, None, first, last)
        goal_cap = sum(b["cap"] for b in goals)
        goal_spent = sum(b["spent"] for b in goals)
        people[p] = {
            "name": cfg.people[p].name,
            "buckets": buckets,
            "goals": totals(goal_cap, goal_spent, sum(b["amount"] for b in fixed),
                            sum(b["amount"] for b in fixed if b["paid"]), month_elapsed(month, today)),
            "unsorted": unsorted,
            "fixed": {"total": sum(b["amount"] for b in fixed),
                      "paid": sum(1 for b in fixed if b["paid"]), "count": len(fixed)},
            "outflow_plan": goal_cap + sum(b["amount"] for b in fixed),
        }

    combined_buckets = {}
    for k, b in cfg.buckets_in(month).items():
        rows = [people[p]["buckets"][k] for p in people]
        if b.kind == "fixed":
            combined_buckets[k] = {"bucket": k, "label": b.label, "kind": b.kind,
                                   "amount": sum(r["amount"] for r in rows),
                                   "paid": sum(1 for r in rows if r["paid"]), "count": len(rows)}
            if b.months:
                parts = [r["installment"] for r in rows]
                combined_buckets[k]["installment"] = {
                    "count": sum(i["count"] for i in parts), "done": sum(i["done"] for i in parts),
                    "total": sum(i["total"] for i in parts), "spent": sum(i["spent"] for i in parts),
                    "left": sum(i["left"] for i in parts)}
        else:
            cap, used = sum(r["cap"] for r in rows), sum(r["spent"] for r in rows)
            combined_buckets[k] = {"bucket": k, "label": b.label, "kind": b.kind, "cap": cap, "spent": used,
                                   "left": cap - used,
                                   "status": pace_status(used, cap, month_elapsed(month, today))}
    g = {k: sum(people[p]["goals"][k] for p in people) for k in ("variable_cap", "variable_spent", "fixed", "fixed_paid")}
    return {
        "month": month,
        "today": today.isoformat(),
        "elapsed": round(month_elapsed(month, today), 4),
        "currency": cfg.currency,
        "people": people,
        "combined": {
            "buckets": combined_buckets,
            "goals": totals(g["variable_cap"], g["variable_spent"], g["fixed"], g["fixed_paid"],
                            month_elapsed(month, today)),
            "unsorted": sum(people[p]["unsorted"] for p in people),
            "fixed": {"paid": sum(people[p]["fixed"]["paid"] for p in people),
                      "count": sum(people[p]["fixed"]["count"] for p in people)},
            "outflow_plan": sum(people[p]["outflow_plan"] for p in people),
        },
        "paid": paid_totals(conn, cfg, month),
        "balance": balance(conn, cfg),
        "pending": pending(conn),
    }

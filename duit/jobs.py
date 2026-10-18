"""Scheduled group messages, written entirely by code (no model involved).

    python -m duit job due     [--send]   House/Car still due this month (1st and 5th)
    python -m duit job recap   [--send]   the week that ends today (Sunday night)
    python -m duit job month   [--send]   report card for last month (on the 1st)
    python -m duit job check   [--send]   integrity check; only posts when something is wrong

Without --send the text is printed. With --send it's posted to `telegram.chat_id` using the bot's
TELEGRAM_BOT_TOKEN (from the environment, else read from the Hermes profile's .env).
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections import defaultdict
from datetime import date

from .config import Config
from .integrity import check
from .ledger import Ledger
from .money import fmt
from .periods import days_between, month_bounds, month_key, prev_month, week_bounds
from .replies import DOT, balance_line
from .report import pace_status, plan_amount, spent

MAX_TELEGRAM = 4000


def due_text(led: Ledger, today: date) -> str | None:
    rows = led.fixed_due(month_key(today))
    if not rows:
        return None
    c = led.cfg.currency
    month = today.strftime("%B")
    lines = [f"⏳ Fixed bills still due for {month}:"]
    for r in rows:
        lines.append(f"@{led.cfg.people[r['person']].name} {led.cfg.buckets[r['bucket']].label} "
                     f"{fmt(r['amount_sen'], c)}")
    lines.append("Reply " + " / ".join(f'"{k} paid"' for k in dict.fromkeys(r["bucket"] for r in rows)) + " when done.")
    return "\n".join(lines)


def _week_target(led: Ledger, person: str, bucket: str, days: list[date]) -> int:
    """Daily budget x the bucket's days in this week, each day priced by its own month's plan."""
    total = 0
    for d in days:
        led.ensure_month(month_key(d))
        total += plan_amount(led.conn, month_key(d), person, bucket)
    return total


def _top_places(led: Ledger, first: date, last: date, n: int = 3) -> list[tuple[str, int, int]]:
    from .backfill import PLACE
    from .ledger import norm_place
    acc: dict[str, list] = defaultdict(lambda: ["", 0, 0])
    for e in led.conn.execute("SELECT place, total_sen FROM entries WHERE deleted_at IS NULL "
                              "AND spent_on BETWEEN ? AND ? AND place != ? AND COALESCE(bucket, '') != 'parents'",
                              (first.isoformat(), last.isoformat(), PLACE)):
        a = acc[norm_place(e["place"]) or e["place"]]
        a[0] = a[0] or e["place"]
        a[1] += 1
        a[2] += e["total_sen"]
    return sorted(((p, k, t) for p, k, t in acc.values()), key=lambda x: -x[2])[:n]


def recap_text(led: Ledger, today: date) -> str:
    """The Mon-Sun week containing `today`: weekday/weekend vs target per person, then the month so far."""
    cfg, c = led.cfg, led.cfg.currency
    monday, sunday = week_bounds(today)
    lines = [f"📅 Week {monday.strftime('%d %b')} – {sunday.strftime('%d %b')}"]
    weekly = [b for b in cfg.buckets.values() if b.kind == "weekly"]
    for p, person in cfg.people.items():
        parts = []
        for b in weekly:
            days = [d for d in days_between(monday, sunday) if d.weekday() in b.days]
            target = _week_target(led, p, b.key, days)
            used = spent(conn=led.conn, person=p, bucket=b.key, start=days[0], end=days[-1]) if days else 0
            diff = target - used
            mark = DOT["over"] if diff < 0 else DOT["ok"]
            word = f"saved {fmt(diff, c)}" if diff >= 0 else f"over {fmt(-diff, c)}"
            parts.append(f"{b.label} {fmt(used, c)}/{fmt(target, c)} ({word}) {mark}")
        lines.append(f"{person.name}: " + " · ".join(parts))
    top = _top_places(led, monday, sunday)
    if top:
        lines.append("Top this week: " + ", ".join(f"{p} {fmt(t, c)}" for p, _, t in top))

    # month so far: only the buckets that need attention
    month = month_key(today)
    st = led.status(month)
    flags = []
    for p, v in st["people"].items():
        for b in v["buckets"].values():
            # a lump sum that exactly uses its budget (e.g. parents) isn't a warning
            if b["kind"] != "fixed" and b["status"] in ("ahead", "over") and b["spent"] != b["cap"]:
                flags.append(f"{v['name']} {b['label']} {fmt(b['spent'], c)}/{fmt(b['cap'], c)} {DOT[b['status']]}")
    g = st["combined"]["goals"]
    lines.append(f"\n{today.strftime('%B')} so far: {fmt(g['spent'], c)} / {fmt(g['cap'], c)} "
                 f"({round(st['elapsed'] * 100)}% of the month) {DOT[g['status']]}")
    lines += [f"• {f}" for f in flags] or ["• Everything on track 🟩"]
    lines.append(balance_line(cfg, st["balance"]))
    if st["pending"]:
        lines.append(f"❓ {len(st['pending'])} still waiting for an answer")
    return "\n".join(lines)


def month_text(led: Ledger, month: str) -> str:
    """Report card for a finished month."""
    cfg, c = led.cfg, led.cfg.currency
    first, last = month_bounds(month)
    st = led.status(month)
    title = first.strftime("%B %Y")
    g = st["combined"]["goals"]
    lines = [f"🧾 {title} report card", f"Together: {fmt(g['spent'], c)} / {fmt(g['cap'], c)} "
             f"→ {'saved ' + fmt(g['left'], c) if g['left'] >= 0 else 'over by ' + fmt(-g['left'], c)} "
             f"{DOT[pace_status(g['spent'], g['cap'], 1.0)]}"]
    for p, v in st["people"].items():
        pg = v["goals"]
        lines.append(f"\n{v['name']}: {fmt(pg['spent'], c)} / {fmt(pg['cap'], c)} "
                     f"{DOT[pace_status(pg['spent'], pg['cap'], 1.0)]}")
        for b in v["buckets"].values():
            if b["kind"] == "fixed":
                continue
            s = pace_status(b["spent"], b["cap"], 1.0)
            note = f"over by {fmt(-b['left'], c)}" if b["left"] < 0 else f"{fmt(b['left'], c)} left"
            lines.append(f"  {b['label']}: {fmt(b['spent'], c)}/{fmt(b['cap'], c)} · {note} {DOT[s]}")
        fixed = [b for b in v["buckets"].values() if b["kind"] == "fixed"]
        lines.append("  " + " · ".join(f"{b['label']} {DOT[b['status']]} {b['status'].upper()}" for b in fixed))
        if v["unsorted"]:
            lines.append(f"  ❓ Unsorted: {fmt(v['unsorted'], c)}")
    top = _top_places(led, first, last, 5)
    if top:
        lines.append("\nTop places: " + ", ".join(f"{p} {k}× {fmt(t, c)}" for p, k, t in top))
    lines.append(balance_line(cfg, st["balance"]))
    return "\n".join(lines)


def check_text(led: Ledger) -> str | None:
    problems = check(led.conn, led.cfg)
    if not problems:
        return None
    return "⚠️ Ledger check found problems:\n" + "\n".join(f"• {p}" for p in problems[:10])


def _token_from_env_file() -> str | None:
    """Read only TELEGRAM_BOT_TOKEN from the Hermes profile's .env (nothing else is loaded)."""
    path = os.path.expanduser(os.environ.get("DUIT_BOT_ENV", "~/.hermes/profiles/kura-kira/.env"))
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip().removeprefix("export ").strip()
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    except OSError:
        return None
    return None


def send(cfg: Config, text: str) -> None:
    """Post to the group via the Telegram Bot API (plain text, split if long)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or _token_from_env_file()
    chat_id = cfg.telegram_chat_id
    if not token or not chat_id:
        raise SystemExit("TELEGRAM_BOT_TOKEN and telegram.chat_id are needed to send")
    for i in range(0, len(text), MAX_TELEGRAM):
        body = json.dumps({"chat_id": chat_id, "text": text[i:i + MAX_TELEGRAM]}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            if not json.load(r).get("ok"):
                raise SystemExit("Telegram refused the message")


def run(led: Ledger, job: str, today: date) -> str | None:
    if job == "due":
        return due_text(led, today)
    if job == "recap":
        return recap_text(led, today)
    if job == "month":
        return month_text(led, prev_month(month_key(today)) if today.day <= 7 else month_key(today))
    if job == "check":
        return check_text(led)
    raise SystemExit(f"unknown job {job!r} (due, recap, month, check)")

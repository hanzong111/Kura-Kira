"""Scheduled group messages, written entirely by code (no model involved).

    python -m duit job due     [--send]   House/Car still due this month (1st and 5th)
    python -m duit job recap   [--send]   the week that ends today (Sunday night)
    python -m duit job month   [--send]   report card for last month (on the 1st)
    python -m duit job check   [--send]   integrity check; only posts when something is wrong

Without --send the text is printed. With --send it's posted to `telegram.chat_id` using the bot's
TELEGRAM_BOT_TOKEN (from the environment, else read from the Hermes profile's .env).
"""

from __future__ import annotations

import html
import json
import os
import re
import urllib.request
from collections import defaultdict
from datetime import date

from .config import Config
from .integrity import check
from .ledger import Ledger
from .money import fmt
from .periods import days_between, month_bounds, month_key, prev_month, week_bounds
from .replies import BUCKET_EMOJI, DOT, balance_line, place_title
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
                              "AND spent_on BETWEEN ? AND ? AND place != ?",
                              (first.isoformat(), last.isoformat(), PLACE)):
        a = acc[norm_place(e["place"]) or e["place"]]
        a[0] = a[0] or e["place"]
        a[1] += 1
        a[2] += e["total_sen"]
    return sorted(((p, k, t) for p, k, t in acc.values()), key=lambda x: -x[2])[:n]


def _week_span(monday: date, sunday: date) -> str:
    if monday.month == sunday.month:
        return f"{monday.day}–{sunday.day} {sunday.strftime('%b')}"
    return f"{monday.day} {monday.strftime('%b')} – {sunday.day} {sunday.strftime('%b')}"


def recap_text(led: Ledger, today: date) -> str:
    """The Mon-Sun week containing `today`: weekday/weekend vs target per person, top places, the month so far."""
    cfg, c = led.cfg, led.cfg.currency
    monday, sunday = week_bounds(today)
    weekly = [b for b in cfg.buckets.values() if b.kind == "weekly"]
    rows: dict[str, dict[str, tuple[int, int]]] = {}  # bucket -> person -> (spent, target)
    for b in weekly:
        days = [d for d in days_between(monday, sunday) if d.weekday() in b.days]
        rows[b.key] = {p: (spent(conn=led.conn, person=p, bucket=b.key, start=days[0], end=days[-1]) if days else 0,
                           _week_target(led, p, b.key, days)) for p in cfg.people}
    saved = sum(t - u for r in rows.values() for u, t in r.values())
    lines = [f"📅 **Weekly recap · {_week_span(monday, sunday)}**",
             f"💰 **{fmt(saved, c)} saved together**" if saved >= 0 else f"🟥 **{fmt(-saved, c)} over together**"]

    def result(u: int, t: int) -> str:
        return f"Saved {fmt(t - u, c)}" if u <= t else f"Over by {fmt(u - t, c)} 🟥"

    for b in weekly:
        r = rows[b.key]
        title = f"{BUCKET_EMOJI.get(b.key, '•')} **{b.label}s**" if b.label.lower().endswith("day") \
            else f"{BUCKET_EMOJI.get(b.key, '•')} **{b.label}**"
        vals = list(r.values())
        if len(vals) > 1 and all(v == vals[0] for v in vals):
            u, t = vals[0]
            lines += ["", f"{title.removesuffix('**')} — both**", f"Each spent {fmt(u, c)} of {fmt(t, c)}",
                      f"{fmt(t - u, c)} saved" if u <= t else f"Over by {fmt(u - t, c)} each 🟥"]
        else:
            lines += ["", title]
            for p, (u, t) in r.items():
                lines += [f"• {cfg.people[p].name}: spent {fmt(u, c)} of {fmt(t, c)}", f"  **{result(u, t)}**"]

    top = _top_places(led, monday, sunday)
    if top:
        lines += ["", "🛍 **Top spending this week**"]
        lines += [f"{n}. {place_title(p)} · {fmt(t, c)}" for n, (p, _, t) in enumerate(top, 1)]

    month = month_key(today)
    st = led.status(month)
    g = st["combined"]["goals"]
    left = f"{fmt(g['left'], c)} left" if g["left"] >= 0 else f"over by {fmt(-g['left'], c)} 🟥"
    used = round(g["spent"] * 100 / g["cap"]) if g["cap"] else 0
    lines += ["", f"📊 **{today.strftime('%B')}: {left}**", f"Spent {fmt(g['spent'], c)} of {fmt(g['cap'], c)}",
              f"Month elapsed: {round(st['elapsed'] * 100)}% · Budget used: {used}%"]
    flags = []
    for k, bucket in cfg.buckets.items():
        hit = [(v["name"], v["buckets"][k]) for v in st["people"].values()
               if k in v["buckets"] and bucket.kind == "monthly" and v["buckets"][k]["status"] in ("ahead", "over")]
        if not hit:
            continue
        if len(hit) == len(st["people"]) > 1 and len({(b["spent"], b["cap"]) for _, b in hit}) == 1:
            b = hit[0][1]   # shared buckets stand the same for both: one line
            flags.append(f"• {b['label']}: {fmt(b['spent'], c)} of {fmt(b['cap'], c)} each {DOT[b['status']]}")
        else:
            flags += [f"• {n} · {b['label']}: {fmt(b['spent'], c)} of {fmt(b['cap'], c)} {DOT[b['status']]}"
                      for n, b in hit]
    lines += ["⚠️ **Keep an eye on**", *flags] if flags else ["✅ Everything on track"]

    o = st["balance"]["owes"]
    lines += ["", "💸 **Settlement**", f"{cfg.people[o['from']].name} owes {cfg.people[o['to']].name} "
              f"**{fmt(o['amount'], c)}**" if o else "All settled ✓"]
    if st["pending"]:
        lines += ["", f"❓ {len(st['pending'])} still waiting for an answer"]
    return "\n".join(lines)


def month_text(led: Ledger, month: str) -> str:
    """Report card for a finished month."""
    cfg, c = led.cfg, led.cfg.currency
    first, last = month_bounds(month)
    st = led.status(month)
    title = first.strftime("%B %Y")
    g = st["combined"]["goals"]
    vleft = g["variable_cap"] - g["variable_spent"]
    lines = [f"🧾 {title} report card", f"Together: {fmt(g['spent'], c)} / {fmt(g['cap'], c)} · spending "
             f"{fmt(g['variable_spent'], c)} / {fmt(g['variable_cap'], c)} "
             f"→ {'saved ' + fmt(vleft, c) if vleft >= 0 else 'over by ' + fmt(-vleft, c)} "
             f"{DOT[pace_status(g['variable_spent'], g['variable_cap'], 1.0)]}"]
    for p, v in st["people"].items():
        pg = v["goals"]
        lines.append(f"\n{v['name']}: {fmt(pg['spent'], c)} / {fmt(pg['cap'], c)} "
                     f"{DOT[pace_status(pg['variable_spent'], pg['variable_cap'], 1.0)]}")
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


def to_html(text: str) -> str:
    """Telegram HTML: escape everything, then **bold** -> <b>bold</b> (same look as the bot's own replies)."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(text, quote=False))


def send(cfg: Config, text: str) -> None:
    """Post to the group via the Telegram Bot API (plain text, split if long)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or _token_from_env_file()
    chat_id = cfg.telegram_chat_id
    if not token or not chat_id:
        raise SystemExit("TELEGRAM_BOT_TOKEN and telegram.chat_id are needed to send")
    for i in range(0, len(text), MAX_TELEGRAM):
        body = json.dumps({"chat_id": chat_id, "text": to_html(text[i:i + MAX_TELEGRAM]),
                           "parse_mode": "HTML"}).encode()
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

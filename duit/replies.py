"""Chat text built from ledger results, so every number the bot posts comes from code."""

from __future__ import annotations

from datetime import date

from .config import Config
from .money import fmt

DOT = {"ok": "🟩", "ahead": "🟨", "over": "🟥", "paid": "✓", "due": "⏳"}


def _name(cfg: Config, person: str | None) -> str:
    if person is None:
        return "?"
    if person == "each":
        return "each paid own"
    return cfg.people[person].name


def _month_name(iso_day: str) -> str:
    return date.fromisoformat(iso_day).strftime("%B")


def week_phrase(cfg: Config, st: dict) -> str:
    """'This weekend: target RM200 + RM20 saved = RM220 · spent RM56.50 · RM163.50 left 🟩'."""
    c = cfg.currency
    w = st["week"]
    span = "This weekend" if st["bucket"] == "weekend" else f"This week ({st['label'].lower()}s)"
    budget = f"target {fmt(w['target'], c)} ({w['days']} × {fmt(w['per_day'], c)})"
    if w["carry"] > 0:
        budget += f" + {fmt(w['carry'], c)} saved = {fmt(w['allowance'], c)}"
    elif w["carry"] < 0:
        budget += f" − {fmt(-w['carry'], c)} overspent = {fmt(w['allowance'], c)}"
    end = (f"over by {fmt(-w['left'], c)} {DOT['over']}" if w["left"] < 0
           else f"{fmt(w['left'], c)} left {DOT[w['status']]}")
    before = f" (incl. {fmt(w['assumed'], c)} before tracking began)" if w.get("assumed") else ""
    return f"{span}: {budget} · spent {fmt(w['spent'], c)}{before} · {end}"


def left_phrase(cfg: Config, st: dict, spent_on: str) -> str:
    """'RM30.00 left in Petrol for October 🟨' / 'over by RM3.00 in Toll for October 🟥'."""
    c = cfg.currency
    span = f"in {st['label']} for {_month_name(spent_on)}"
    if st["left"] < 0:
        return f"over by {fmt(-st['left'], c)} {span} {DOT['over']}"
    return f"{fmt(st['left'], c)} left {span} {DOT[st['status']]}"


def budget_phrase(cfg: Config, st: dict, spent_on: str) -> str:
    return week_phrase(cfg, st) if "week" in st else left_phrase(cfg, st, spent_on)


def spend_reply(cfg: Config, e: dict) -> str:
    """The one-to-three line confirmation after logging, editing or resolving a spend."""
    c = cfg.currency
    if e.get("duplicate"):
        return f"Already logged as #{e['id']}."
    bucket = cfg.buckets[e["bucket"]].label if e["bucket"] else "❓ Unsorted"
    head = f"✅ #{e['id']} {e['place']} · {bucket} · {fmt(e['total_sen'], c)}"
    shares = e["shares"]
    if len(shares) == 1:
        (person, _), = shares.items()
        head += f" · {_name(cfg, person)}"
        if e["paid_by"] not in (person, None):
            head += f" · paid by {_name(cfg, e['paid_by'])}"
    else:
        b = cfg.buckets.get(e["bucket"]) if e["bucket"] else None
        if b and b.shared and not e.get("shares_given"):
            head += " · shared"
        head += f" · paid by {_name(cfg, e['paid_by'])}"
    lines = [head]
    status = e.get("status") or {}
    if len(shares) == 1:
        (person, _), = shares.items()
        if person in status:
            st = status[person]
            if "week" in st:
                lines.append(f"   {week_phrase(cfg, st)}")
            else:
                lines[0] += f" — {left_phrase(cfg, st, e['spent_on'])}"
    else:
        for person, amt in shares.items():
            line = f"   {_name(cfg, person)} {fmt(amt, c)}"
            if person in status:
                line += f" → {budget_phrase(cfg, status[person], e['spent_on'])}"
            lines.append(line)
    for a in e.get("alerts") or []:
        lines.append(alert_line(cfg, a))
    return "\n".join(lines)


def alert_line(cfg: Config, a: dict) -> str:
    c = cfg.currency
    label = cfg.buckets[a["bucket"]].label
    scope = "this week" if a["scope"] == "week" else "this month"
    who = _name(cfg, a["person"])
    if a["threshold"] >= 1:
        return f"🟥 {who} · {label} over {scope} by {fmt(-a['left'], c)} ({fmt(a['spent'], c)}/{fmt(a['cap'], c)})"
    return (f"⚠️ {who} · {label} at {a['spent'] * 100 // max(a['cap'], 1)}% {scope} "
            f"({fmt(a['spent'], c)}/{fmt(a['cap'], c)}), {fmt(a['left'], c)} left")


def question(cfg: Config, e: dict) -> dict | None:
    """What to ask in the group for a pending entry, or None if nothing is missing."""
    c = cfg.currency
    who = [cfg.people[p].name for p in e["shares"]]
    what = f"#{e['id']} {e['place']} {fmt(e['total_sen'], c)}"
    if len(e["shares"]) > 1:
        what += " (" + " · ".join(f"{cfg.people[p].name} {fmt(a, c)}" for p, a in e["shares"].items()) + ")"
    if "payer" in e["needs"]:
        tag = sorted(set(who) | {cfg.people[e["sender"]].name})
        options = [p.name for p in cfg.people.values()] + ["Each paid own"]
        return {"entry_id": e["id"], "asks": "payer", "tag": tag,
                "text": f"{' '.join('@' + t for t in tag)} {what}: who paid?\nReply: {' / '.join(options)}",
                "options": options}
    if "bucket" in e["needs"]:
        opts = e.get("bucket_options") or ["daily", "extra"]
        labels = ["Everyday (weekday/weekend)" if o == "daily" else cfg.buckets[o].label for o in opts
                  if o == "daily" or o in cfg.buckets]
        labels += ["Other"]
        return {"entry_id": e["id"], "asks": "bucket", "tag": [cfg.people[e["sender"]].name],
                "text": f"@{cfg.people[e['sender']].name} {what}: which one?\nReply: {' / '.join(labels)}",
                "options": labels}
    return None


def fixed_reply(cfg: Config, r: dict) -> str:
    label = cfg.buckets[r["bucket"]].label
    month = date.fromisoformat(r["month"] + "-01").strftime("%B")
    if r["already_paid"]:
        return f"{label} is already marked paid for {month}."
    return f"✅ {label} {fmt(r['amount'], cfg.currency)} · {_name(cfg, r['person'])} · Paid for {month}"


def balance_line(cfg: Config, bal: dict) -> str:
    o = bal["owes"]
    if not o:
        return "Balance: all settled."
    return f"Balance: {_name(cfg, o['from'])} owes {_name(cfg, o['to'])} {fmt(o['amount'], cfg.currency)}"


def status_text(cfg: Config, st: dict, person: str | None = None) -> str:
    """Text version of the dashboard for 'how are we doing?' / 'how much left?'."""
    c = cfg.currency
    month = date.fromisoformat(st["month"] + "-01").strftime("%B %Y")
    out = [f"📊 {month} · {round(st['elapsed'] * 100)}% through the month"]
    g = st["combined"]["goals"]
    if person is None:
        out.append(f"Together: {fmt(g['spent'], c)} / {fmt(g['cap'], c)} {DOT[g['status']]}")
    for p, v in st["people"].items():
        if person and p != person:
            continue
        pg = v["goals"]
        out.append(f"\n{v['name']}: {fmt(pg['spent'], c)} / {fmt(pg['cap'], c)} {DOT[pg['status']]}")
        for b in v["buckets"].values():
            if b["kind"] == "fixed":
                continue
            if "week" in b:
                out.append(f"  {week_phrase(cfg, b)}")
            else:
                out.append(f"  {b['label']}: {fmt(b['left'], c)} left ({fmt(b['spent'], c)}/{fmt(b['cap'], c)}) "
                           f"{DOT[b['status']]}")
        fixed = [b for b in v["buckets"].values() if b["kind"] == "fixed"]
        out.append("  " + " · ".join(f"{b['label']} {DOT[b['status']]} {b['status'].upper()}" for b in fixed))
        if v["unsorted"]:
            out.append(f"  ❓ Unsorted: {fmt(v['unsorted'], c)}")
    out.append("\n" + balance_line(cfg, st["balance"]))
    if st["pending"]:
        out.append(f"❓ {len(st['pending'])} waiting for an answer")
    return "\n".join(out)


def bucket_text(cfg: Config, st: dict, bucket: str, person: str | None = None) -> str:
    """One bucket for one or both people ('how much left for weekend?')."""
    c = cfg.currency
    b = cfg.buckets[bucket]
    lines = []
    for p, v in st["people"].items():
        if person and p != person:
            continue
        s = v["buckets"][bucket]
        if s["kind"] == "fixed":
            lines.append(f"{v['name']} · {b.label} {fmt(s['amount'], c)} {DOT[s['status']]} {s['status'].upper()}")
        elif "week" in s:
            lines.append(f"{v['name']} · {week_phrase(cfg, s)}")
        else:
            lines.append(f"{v['name']} · {b.label}: {fmt(s['left'], c)} left "
                         f"({fmt(s['spent'], c)}/{fmt(s['cap'], c)}) {DOT[s['status']]}")
    return "\n".join(lines)


def spends_text(cfg: Config, rows: list[dict], month: str, person: str | None, filters: dict, limit: int) -> str:
    """Search result with the total computed here ('what did we spend on food?')."""
    c = cfg.currency
    label = [date.fromisoformat(month + "-01").strftime("%B %Y")]
    if person:
        label.append(cfg.people[person].name)
    for k in ("bucket", "category", "query"):
        if filters.get(k):
            label.append(str(filters[k]).title() if k != "query" else f"“{filters[k]}”")
    amount = (lambda r: r["shares"].get(person, 0)) if person else (lambda r: r["total_sen"])
    total = sum(amount(r) for r in rows)
    out = [f"🔎 {' · '.join(label)}: {len(rows)} spend{'s' if len(rows) != 1 else ''}, total {fmt(total, c)}"]
    for r in rows[:limit]:
        where = cfg.buckets[r["bucket"]].label if r["bucket"] else "Unsorted"
        cat = f" · {r['category']}" if r["category"] else ""
        day = date.fromisoformat(r["spent_on"]).strftime("%d %b")
        out.append(f"#{r['id']} {day} {r['place']} {fmt(amount(r), c)} ({where}{cat})")
    if len(rows) > limit:
        out.append(f"…and {len(rows) - limit} more")
    return "\n".join(out)

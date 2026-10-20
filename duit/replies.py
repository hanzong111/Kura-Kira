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


BUCKET_EMOJI = {"weekday": "🗓", "weekend": "🌤", "extra": "✨", "grocery": "🛒", "chuchu": "🐱", "petrol": "⛽",
                "toll": "🛣️", "parents": "👪", "house": "🏠", "car": "🚗"}


def _pct(spent: int, cap: int) -> int:
    return round(spent * 100 / cap) if cap else (0 if spent == 0 else 100)


def place_title(place: str) -> str:
    """'watson' -> 'Watson'; names with their own capitals stay as typed."""
    return place[:1].upper() + place[1:] if place[:1].islower() else place


def _budget_block(cfg: Config, e: dict) -> list[str]:
    """How the spend's bucket now stands for everyone who bears it (as one line when they stand the same)."""
    c = cfg.currency
    status = {p: s for p, s in (e.get("status") or {}).items() if p in e["shares"]}
    if not status:
        return []
    weekly = all("week" in s for s in status.values())
    view = {p: (s["week"] if weekly else s) for p, s in status.items()}
    cap_key = "allowance" if weekly else "cap"
    states = {v["status"] for v in view.values()} | ({"ahead"} if e.get("alerts") else set())
    head = "🟥" if any(v["left"] < 0 for v in view.values()) else "⚠️" if "ahead" in states else "🟩"
    b = cfg.buckets[e["bucket"]]
    title = (("Budget this weekend" if b.key == "weekend" else f"{b.label} budget this week") if weekly
             else f"{_month_name(e['spent_on'])} {b.label} budget")
    rows = list(view.items())
    alike = len(rows) > 1 and all((v["left"], v[cap_key], v["spent"]) == (rows[0][1]["left"], rows[0][1][cap_key],
                                                                          rows[0][1]["spent"]) for _, v in rows)

    def left(v: dict, each: str = "") -> str:
        return f"Over by {fmt(-v['left'], c)}{each}" if v["left"] < 0 else f"{fmt(v['left'], c)} left{each}"

    def carry(v: dict) -> str | None:
        if not weekly or not v["carry"]:
            return None
        return (f"Target {fmt(v['target'], c)} + {fmt(v['carry'], c)} carried forward" if v["carry"] > 0
                else f"Target {fmt(v['target'], c)} − {fmt(-v['carry'], c)} overspent earlier")

    if len(rows) == 1 or alike:
        v = rows[0][1]
        out = [f"{head} **{title}{' — per person' if alike else ''}**", f"**{left(v, ' each' if alike else '')}**",
               f"{fmt(v['spent'], c)} of {fmt(v[cap_key], c)} spent · **{_pct(v['spent'], v[cap_key])}% used**"]
        return out + [x for x in [carry(v)] if x]
    out = [f"{head} **{title}**"]
    for p, v in rows:
        out.append(f"• {_name(cfg, p)}: **{left(v)}** · {fmt(v['spent'], c)} of {fmt(v[cap_key], c)} "
                   f"({_pct(v['spent'], v[cap_key])}%)")
        if carry(v):
            out.append(f"  {carry(v)}")
    return out


def spend_reply(cfg: Config, e: dict, verb: str = "recorded") -> str:
    """The confirmation after logging, editing or resolving a spend: what it was, who paid, whose it is,
    and how that bucket now stands."""
    c = cfg.currency
    if e.get("duplicate"):
        return f"Already logged as #{e['id']}."
    b = cfg.buckets.get(e["bucket"]) if e["bucket"] else None
    icon = "✏️" if verb == "updated" else "✅"
    lines = [f"{icon} **Expense {verb} · #{e['id']}**", ""]
    place = place_title(e["place"])
    named_as_bucket = b is not None and _squash(e["place"]) in (_squash(b.key), _squash(b.label))
    lines.append(f"{BUCKET_EMOJI.get(e['bucket'], '❓')} **{b.label if named_as_bucket else place} · "
                 f"{fmt(e['total_sen'], c)}**")
    if not named_as_bucket:
        lines.append(" · ".join(x for x in (b.label if b else "❓ Unsorted", e.get("category")) if x))

    shares, payer = e["shares"], e["paid_by"]
    if payer == "each":
        lines.append("Each paid their own")
    else:
        paid = f"Paid by **{_name(cfg, payer)}**"
        if len(shares) == 1:
            (owner, _), = shares.items()
            lines.append(paid if owner == payer else f"{paid} · For **{_name(cfg, owner)}**")
        else:
            even = max(shares.values()) - min(shares.values()) <= 1
            lines.append(f"{paid} · {'Split equally' if even else 'Split'}")
    if len(shares) > 1:
        lines.append(" · ".join(f"{_name(cfg, p)}: {fmt(a, c)}" for p, a in shares.items()))

    block = _budget_block(cfg, e) if b else []
    return "\n".join(lines + ([""] + block if block else []))


def _squash(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


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
    line = f"✅ {label} {fmt(r['amount'], cfg.currency)} · {_name(cfg, r['person'])} · Paid for {month}"
    i = r.get("installment")
    if i:
        line += (f" ({i['done']} of {i['count']} paid, " +
                 (f"{fmt(i['left'], cfg.currency)} to go)" if i["left"] else "all done 🎉)"))
    return line


def balance_line(cfg: Config, bal: dict) -> str:
    o = bal["owes"]
    if not o:
        return "Balance: all settled."
    return f"Balance: {_name(cfg, o['from'])} owes {_name(cfg, o['to'])} {fmt(o['amount'], cfg.currency)}"


def _plural(label: str) -> str:
    return label + "s" if label.lower().endswith("day") else label


def _left_word(cfg: Config, b: dict) -> str:
    """How a monthly bucket stands: 'RM35.25 left ⚠️' (ahead of pace), 'fully used ⚠️', 'over by RM5.00 🟥'."""
    c = cfg.currency
    if b["left"] < 0:
        return f"over by {fmt(-b['left'], c)} 🟥"
    if b["left"] == 0 and b["cap"]:
        return "fully used ⚠️"
    return f"{fmt(b['left'], c)} left" + (" ⚠️" if b["status"] == "ahead" else "")


def _month_left(cfg: Config, g: dict) -> str:
    c = cfg.currency
    return f"{fmt(g['left'], c)} left" if g["left"] >= 0 else f"over by {fmt(-g['left'], c)} 🟥"


def status_text(cfg: Config, st: dict, person: str | None = None) -> str:
    """'How are we doing?': left this month, this week's allowance, other balances, bills, settlement.
    Every number comes from the status dict (the ledger); this only lays them out."""
    c = cfg.currency
    month = date.fromisoformat(st["month"] + "-01").strftime("%B %Y")
    who = [p for p in st["people"] if person in (None, p)]
    g = st["combined"]["goals"] if person is None else st["people"][person]["goals"]
    used = round(g["spent"] * 100 / g["cap"]) if g["cap"] else 0
    out = [f"📊 **DUIT · {month}**", f"Month elapsed: {round(st['elapsed'] * 100)}% · Budget used: {used}%"]
    if person is None:
        out += ["", f"💰 **Together: {_month_left(cfg, g)}**", f"Spent {fmt(g['spent'], c)} of {fmt(g['cap'], c)}"]

    for p in who:
        v = st["people"][p]
        out += ["", f"{cfg.people[p].emoji} **{v['name']} · {_month_left(cfg, v['goals'])} this month**"]
        if person:
            out.append(f"Spent {fmt(v['goals']['spent'], c)} of {fmt(v['goals']['cap'], c)}")
        for b in v["buckets"].values():
            if b["kind"] != "weekly":
                continue
            w = b.get("week")
            if not w:  # not the current month: the whole month's figure
                out.append(f"• {_plural(b['label'])}: **{_left_word(cfg, b)}**")
                continue
            left = (f"{fmt(w['left'], c)} left" if w["left"] > 0 else "fully used ⚠️" if w["left"] == 0
                    else f"over by {fmt(-w['left'], c)} 🟥")
            out.append(f"• {_plural(b['label'])}: **{left}**")
            if w["carry"] > 0:
                out.append(f"  Includes {fmt(w['carry'], c)} carried forward")
            elif w["carry"] < 0:
                out.append(f"  After {fmt(-w['carry'], c)} overspent earlier this month")
        if v["unsorted"]:
            out.append(f"• ❓ Unsorted: {fmt(v['unsorted'], c)}")

    # monthly buckets: one line when everyone stands the same (shared buckets always do), else one line per person
    same, differ = [], []
    for k, bucket in cfg.buckets.items():
        rows = [st["people"][p]["buckets"][k] for p in who if k in st["people"][p]["buckets"]]
        if bucket.kind != "monthly" or not rows:
            continue
        alike = all((r["left"], r["cap"], r["status"]) == (rows[0]["left"], rows[0]["cap"], rows[0]["status"])
                    for r in rows)
        (same if alike else differ).append(k)
    if same:
        out += ["", f"🛒 **Other monthly balances{' — per person' if len(who) > 1 else ''}**"]
        out += [f"• {cfg.buckets[k].label}: {_left_word(cfg, st['people'][who[0]]['buckets'][k])}" for k in same]
    for k in differ:
        out += ["", f"{BUCKET_EMOJI.get(k, '•')} **{cfg.buckets[k].label} remaining**",
                " · ".join(f"{st['people'][p]['name']}: {_left_word(cfg, st['people'][p]['buckets'][k]).removesuffix(' left')}"
                           for p in who)]

    due = [(p, b) for p in who for b in st["people"][p]["buckets"].values() if b["kind"] == "fixed" and not b["paid"]]
    if not due:
        whom = "" if len(who) == 1 else " for both" if len(who) == 2 else " for everyone"
        out += ["", f"✅ **All fixed bills paid{whom}**"]
    else:
        out += ["", "⏳ **Fixed bills due**"]
        for p in who:
            mine = [b for q, b in due if q == p]
            if mine:
                out.append(f"• {st['people'][p]['name']}: " + ", ".join(f"{b['label']} {fmt(b['amount'], c)}" for b in mine))

    o = st["balance"]["owes"]
    out += ["", "💸 **Settlement**",
            f"{_name(cfg, o['from'])} owes {_name(cfg, o['to'])} **{fmt(o['amount'], c)}**" if o else "All settled ✓"]
    if st["pending"]:
        out += ["", f"❓ {len(st['pending'])} waiting for an answer"]
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

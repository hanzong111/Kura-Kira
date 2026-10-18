"""Invariant checks and backups. Run `python -m duit check` / `python -m duit backup` (also nightly)."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from .config import Config
from .report import balance

KEEP_BACKUPS = 30


def check(conn: sqlite3.Connection, cfg: Config) -> list[str]:
    """Everything that must always be true about the ledger. Empty list = healthy."""
    problems = []
    people = set(cfg.people)
    spend_buckets = {k for k, b in cfg.buckets.items() if b.kind != "fixed"}
    for e in conn.execute("SELECT * FROM entries WHERE deleted_at IS NULL"):
        shares = conn.execute("SELECT person, amount_sen FROM shares WHERE entry_id=?", (e["id"],)).fetchall()
        tag = f"#{e['id']} {e['place']}"
        if not shares:
            problems.append(f"{tag}: has no shares")
        if sum(s["amount_sen"] for s in shares) != e["total_sen"]:
            problems.append(f"{tag}: shares add up to {sum(s['amount_sen'] for s in shares)} sen, total is {e['total_sen']}")
        for s in shares:
            if s["person"] not in people:
                problems.append(f"{tag}: share for unknown person {s['person']!r}")
        if e["bucket"] is not None and e["bucket"] not in spend_buckets:
            problems.append(f"{tag}: unknown bucket {e['bucket']!r}")
        elif e["bucket"] and cfg.buckets[e["bucket"]].shared and not e["shares_given"]:
            amounts = {s["person"]: s["amount_sen"] for s in shares}
            if set(amounts) != people or max(amounts.values()) - min(amounts.values()) > 1:
                problems.append(f"{tag}: {e['bucket']} is shared but isn't split evenly between everyone")
        if e["paid_by"] is not None and e["paid_by"] not in people | {"each"}:
            problems.append(f"{tag}: unknown payer {e['paid_by']!r}")
        if e["sender"] not in people:
            problems.append(f"{tag}: unknown sender {e['sender']!r}")
        try:
            day = date.fromisoformat(e["spent_on"])
            if e["bucket"] in spend_buckets and cfg.buckets[e["bucket"]].kind == "weekly" \
                    and day.weekday() not in cfg.buckets[e["bucket"]].days:
                problems.append(f"{tag}: {e['bucket']} bucket but spent on a {day.strftime('%A')}")
        except ValueError:
            problems.append(f"{tag}: bad date {e['spent_on']!r}")
    orphans = conn.execute("SELECT COUNT(*) FROM shares WHERE entry_id NOT IN (SELECT id FROM entries)").fetchone()[0]
    if orphans:
        problems.append(f"{orphans} shares belong to no entry")
    net = balance(conn, cfg)["net"]
    if sum(net.values()) != 0:
        problems.append(f"balance doesn't net to zero: {net}")
    for s in conn.execute("SELECT * FROM settlements WHERE deleted_at IS NULL"):
        if s["from_person"] not in people or s["to_person"] not in people or s["from_person"] == s["to_person"]:
            problems.append(f"settlement #{s['id']}: bad people {s['from_person']}→{s['to_person']}")
    for f in conn.execute("""SELECT f.month, f.person, f.bucket, f.amount_sen, p.amount_sen AS plan FROM fixed_payments f
                             JOIN plans p ON p.month = f.month AND p.person = f.person AND p.bucket = f.bucket
                             WHERE f.amount_sen != p.amount_sen"""):
        problems.append(f"{f['month']} {f['person']} {f['bucket']}: bill is {f['amount_sen']} sen but the plan says {f['plan']}")
    months = {r[0][:7] for r in conn.execute("SELECT DISTINCT spent_on FROM entries WHERE deleted_at IS NULL")}
    planned = {r[0] for r in conn.execute("SELECT DISTINCT month FROM plans")}
    for m in sorted(months - planned):
        problems.append(f"{m}: spends but no plan")
    return problems


def backup(conn: sqlite3.Connection, dest_dir: Path, keep: int = KEEP_BACKUPS) -> Path:
    """Consistent copy via SQLite's online backup (safe while the bot is writing). Keeps the newest `keep`."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"duit-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    target = sqlite3.connect(dest)
    try:
        conn.backup(target)
    finally:
        target.close()
    for old in sorted(dest_dir.glob("duit-*.db"))[:-keep]:
        old.unlink()
    return dest

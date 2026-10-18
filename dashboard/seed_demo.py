"""Fill a demo ledger (data/demo.db) with a realistic month, through the Ledger API only.

    python3 -m dashboard.seed_demo               # rebuilds data/demo.db as of 2026-10-17
    python3 -m dashboard.seed_demo --db /tmp/x.db
    DUIT_DB=data/demo.db python3 -m dashboard.server

The month has: the example rows from docs/design-prompt.md, a split Zapfan lunch, Hanz over budget on
Toll, Vanisa overspending one weekend (so this
weekend starts with a negative carry-over), an Unsorted Watsons entry, a dinner with no payer, a settle-up, and Hanz's house paid / car due.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from duit import config, db
from duit.ledger import Ledger

DEMO_DB = config.ROOT / "data" / "demo.db"
TODAY = "2026-10-17T13:00"  # Saturday, day 17/31

# (day, sender, place, amount or shares, bucket, category, extra kwargs)
SEPTEMBER = [
    ("2026-09-05", "hanz", "Sushi-Mentai", 48.90, "daily", "Food", {}),
    ("2026-09-12", "vanisa", "Jaya Grocer", 96.40, "grocery", "Groceries", {}),
    ("2026-09-19", "hanz", "Petronas", 70, "petrol", "Transport", {}),
]

OCTOBER = [
    ("2026-10-01", "hanz", "Zapfan", 12.80, "daily", "Food", {"item": "lunch"}),
    ("2026-10-02", "vanisa", "Kopi Corner", 9.50, "daily", "Food", {"item": "breakfast"}),
    ("2026-10-03", "hanz", "Sushi-Mentai", {"hanz": 52, "vanisa": 52}, "daily", "Food", {"paid_by": "hanz"}),
    ("2026-10-03", "vanisa", "Jaya Grocer", 64.30, "grocery", "Groceries", {}),
    ("2026-10-04", "hanz", "GSC Mid Valley", {"hanz": 28, "vanisa": 28}, "daily", "Leisure",
     {"item": "movie", "paid_by": "vanisa"}),
    ("2026-10-04", "vanisa", "Uniqlo", 89.90, "extra", "Shopping", {}),
    ("2026-10-05", "hanz", "Petronas", 80, "petrol", "Transport", {}),
    ("2026-10-05", "hanz", "Touch 'n Go reload", 30, "toll", "Transport", {}),
    ("2026-10-06", "vanisa", "Zapfan", 13.90, "daily", "Food", {"item": "lunch"}),
    ("2026-10-07", "hanz", "Badminton court", 30, "daily", "Sport", {}),
    ("2026-10-08", "vanisa", "Shell", 60, "petrol", "Transport", {}),
    ("2026-10-09", "hanz", "Grab", 18.40, "daily", "Transport", {}),
    ("2026-10-10", "hanz", "Sushi-Mentai", 56.50, "daily", "Food", {}),
    ("2026-10-10", "vanisa", "Pavilion", 380, "daily", "Shopping", {"item": "birthday gift"}),
    ("2026-10-10", "vanisa", "Pet Lovers", 38, "chuchu", "Pet", {"item": "cat litter"}),
    ("2026-10-11", "hanz", "Jaya Grocer", {"hanz": 46.60, "vanisa": 46.60}, "grocery", "Groceries",
     {"paid_by": "hanz"}),
    ("2026-10-11", "hanz", "Hawker centre", {"hanz": 21, "vanisa": 21}, "daily", "Food",
     {"paid_by": "each", "item": "dinner"}),
    ("2026-10-12", "vanisa", "Kopi Corner", 11.20, "daily", "Food", {}),
    ("2026-10-13", "hanz", "Touch 'n Go reload", 23, "toll", "Transport", {}),
    ("2026-10-13", "vanisa", "Zapfan", 14.20, "daily", "Food", {"item": "lunch"}),
    ("2026-10-14", "hanz", "Badminton court", 30, "daily", "Sport", {}),
    ("2026-10-14", "vanisa", "Guardian", 18.50, "chuchu", "Toiletries", {}),
    ("2026-10-15", "hanz", "Zapfan", {"hanz": 13.20, "vanisa": 14.50}, "daily", "Food",
     {"item": "lunch", "paid_by": "hanz"}),
    ("2026-10-15", "hanz", "Jaya Grocer", 72.80, "grocery", "Groceries", {}),
    ("2026-10-16", "vanisa", "Petronas", 50, "petrol", "Transport", {}),
    ("2026-10-16", "hanz", "Kopi Corner", 8.90, "daily", "Food", {}),
    # no payer given and two people involved -> the bot asks who paid
    ("2026-10-16", "vanisa", "Nando's", {"hanz": 38.50, "vanisa": 31.20}, "daily", "Food", {"item": "dinner"}),
    # bucket unclear -> Unsorted, the bot asks Toiletries or Extra
    ("2026-10-16", "vanisa", "Watsons", 75, None, "Toiletries", {"bucket_options": ["chuchu", "extra"]}),
    ("2026-10-17", "hanz", "Sushi-Mentai", 56.50, "daily", "Food", {}),
    ("2026-10-17", "vanisa", "Hair salon", 45, "daily", "Shopping", {}),
]


def seed(path: Path, today: str = TODAY) -> Ledger:
    for p in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        p.unlink(missing_ok=True)
    clock_now = datetime.fromisoformat(today)
    cfg = config.load()
    ledger = Ledger(db.connect(path), cfg, lambda: clock_now.replace(tzinfo=cfg.tz))

    for rows in (SEPTEMBER, OCTOBER):
        for day, sender, place, amount, bucket, category, extra in rows:
            amount_kw = {"shares": amount} if isinstance(amount, dict) else {"total": amount}
            ledger.log_spend(sender=sender, place=place, bucket=bucket, category=category, spent_on=day,
                             **amount_kw, **extra)
    ledger.pay_fixed("hanz", "house", "2026-09")
    ledger.pay_fixed("hanz", "car", "2026-09")
    ledger.pay_fixed("vanisa", "parents", "2026-09")
    ledger.pay_fixed("hanz", "parents", "2026-10")
    ledger.pay_fixed("vanisa", "parents", "2026-10")
    ledger.settle(from_person="vanisa", to_person="hanz", amount=40, on="2026-10-06")
    ledger.pay_fixed("hanz", "house", "2026-10")  # car stays Due
    return ledger


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=DEMO_DB)
    ap.add_argument("--today", default=TODAY, help="seed clock, YYYY-MM-DDTHH:MM (Malaysia time)")
    args = ap.parse_args()
    if args.db.name == "duit.db":
        raise SystemExit(f"refusing to overwrite the real ledger {args.db}: pick another file name")
    ledger = seed(args.db, args.today)
    st = ledger.status(args.today[:7])
    n = len(ledger.list_entries(args.today[:7]))
    print(f"seeded {args.db}: {n} entries in {st['month']}, pending {len(st['pending'])}")


if __name__ == "__main__":
    main()

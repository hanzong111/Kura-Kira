"""Quick look at the ledger from the terminal: `python -m duit status [YYYY-MM]`."""

import json
import sys

from . import config, db
from .ledger import Ledger
from .money import fmt


def main(argv: list[str]) -> int:
    cfg = config.load()
    led = Ledger(db.connect(), cfg)
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        st = led.status(argv[1] if len(argv) > 1 else None)
        c = cfg.currency
        print(f"{st['month']}  (today {st['today']}, {st['elapsed']:.0%} of the month)")
        for p, v in st["people"].items():
            g = v["goals"]
            print(f"\n{v['name']}: {fmt(g['spent'], c)} / {fmt(g['cap'], c)}  [{g['status']}]")
            for b in v["buckets"].values():
                if b["kind"] == "fixed":
                    print(f"  {b['label']:<22} {fmt(b['amount'], c):>11}  {b['status'].upper()}")
                    continue
                line = f"  {b['label']:<22} {fmt(b['spent'], c):>11} / {fmt(b['cap'], c):<11} [{b['status']}]"
                if "week" in b:
                    w = b["week"]
                    line += (f"   this week {fmt(w['spent'], c)} / {fmt(w['allowance'], c)} "
                             f"(target {fmt(w['target'], c)} {'+' if w['carry'] >= 0 else '-'} {fmt(abs(w['carry']), c)})")
                print(line)
            if v["unsorted"]:
                print(f"  {'Unsorted':<22} {fmt(v['unsorted'], c):>11}")
        owes = st["balance"]["owes"]
        print("\nBalance:", f"{cfg.people[owes['from']].name} owes {cfg.people[owes['to']].name} "
              f"{fmt(owes['amount'], c)}" if owes else "settled")
        if st["pending"]:
            print(f"Needs answer: {len(st['pending'])}")
    elif cmd == "json":
        print(json.dumps(led.status(argv[1] if len(argv) > 1 else None), indent=2))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

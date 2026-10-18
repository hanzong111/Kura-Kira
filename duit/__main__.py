"""Ledger from the terminal:
    python -m duit status [YYYY-MM]   month overview
    python -m duit json [YYYY-MM]     raw status JSON
    python -m duit check              invariant checks (exit 1 on problems)
    python -m duit backup             online backup to data/backups (keeps 30)
    python -m duit backfill FROM TO   on-budget placeholder spends for days before tracking
    python -m duit job NAME [--send]  scheduled message: due | recap | month | check
    python -m duit reshare            re-apply who-bears-it rules (after changing `shared` buckets)
"""

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
    elif cmd == "check":
        from .integrity import check
        problems = check(led.conn, cfg)
        print("\n".join(problems) if problems else "ledger OK ✓")
        return 1 if problems else 0
    elif cmd == "backup":
        from .config import ROOT
        from .integrity import backup
        print(backup(led.conn, ROOT / "data" / "backups"))
    elif cmd == "backfill":
        from datetime import date

        from .backfill import backfill
        for r in backfill(led, date.fromisoformat(argv[1]), date.fromisoformat(argv[2])):
            print(f"{'(exists) ' if r['duplicate'] else ''}#{r['id']} {cfg.people[r['person']].name} {r['bucket']} "
                  f"{r['from']}..{r['to']} {fmt(r['amount'], cfg.currency)}")
    elif cmd == "job":
        from .jobs import run, send
        text = run(led, argv[1], led.today())
        if text is None:
            print("(nothing to send)")
        elif "--send" in argv:
            send(cfg, text)
            print("sent")
        else:
            print(text)
    elif cmd == "reshare":
        changed = led.reshare()
        for c in changed:
            print(f"#{c['id']} {c['place']}: {c['before']} -> {c['after']}")
        if changed:
            led.conn.execute("INSERT INTO audit(at, tool, args, result, ok) VALUES (?, 'cli_reshare', '{}', ?, 1)",
                             (led.now().isoformat(timespec="seconds"), json.dumps(changed)))
        print(f"{len(changed)} entries re-split")
    elif cmd == "json":
        print(json.dumps(led.status(argv[1] if len(argv) > 1 else None), indent=2))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

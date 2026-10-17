"""Run the parsing test set against the real agent (`hermes -p kura-kira -z ...`).

Each case gets a fresh ledger. The sender/chat/message ids are passed the way the gateway does
(HERMES_SESSION_* — the plugin falls back to the environment outside the gateway). Then the ledger
is checked against `expect` in cases.toml.

    .venv/bin/python eval/run.py                 # all cases
    .venv/bin/python eval/run.py -k split -m gpt-5.6-luna
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import tomllib
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from duit import config, db  # noqa: E402
from duit.ledger import Ledger  # noqa: E402
from duit.tools import Context, Tools  # noqa: E402

IDS = {"hanz": "1001", "vanisa": "1002"}
CHAT = "-100777"


def eval_config(tmp: Path) -> Path:
    text = (ROOT / "config.example.toml").read_text()
    text = text.replace("[people.hanz]\nname = \"Hanz\"\ntelegram_id = 0", f"[people.hanz]\nname = \"Hanz\"\ntelegram_id = {IDS['hanz']}")
    text = text.replace("[people.vanisa]\nname = \"Vanisa\"\ntelegram_id = 0", f"[people.vanisa]\nname = \"Vanisa\"\ntelegram_id = {IDS['vanisa']}")
    p = tmp / "config.toml"
    p.write_text(text)
    return p


def norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def sen(rm) -> int:
    return round(float(rm) * 100)


def daily_bucket(day: date) -> str:
    return "weekend" if day.weekday() >= 5 else "weekday"


def seed(cases: dict, case_id: str, tools: Tools) -> dict | None:
    """Put the ledger in the state the `after` case should have produced (deterministically, no LLM)."""
    c = cases[case_id]
    e = c["expect"]
    args = {"place": e.get("place") or c["text"].split()[0], "raw_text": c["text"]}
    if "shares" in e:
        args["shares"] = e["shares"]
    else:
        args["amount"] = e["amount"]
    if e.get("paid_by"):
        args["paid_by"] = e["paid_by"]
    if e.get("bucket") and not e.get("asked"):
        args["bucket"] = e["bucket"]
    elif e.get("asked") and "payer" not in e.get("needs", []):
        args["bucket_options"] = ["daily", "extra"]
    elif "payer" in e.get("needs", []) and not e.get("bucket"):
        args["bucket"] = "daily"
    elif e.get("bucket"):
        args["bucket"] = e["bucket"]
    if e.get("category") and not e.get("asked"):
        args["category"] = e["category"]
    return tools.call("duit_log_spend", args, Context(sender_telegram_id=IDS[c["sender"]], chat_id=CHAT, msg_id="seed"))


def run_agent(text: str, sender: str, msg_id: str, env_base: dict, model: str | None, timeout: int) -> tuple[str, float]:
    env = {**env_base, "HERMES_SESSION_USER_ID": IDS[sender], "HERMES_SESSION_CHAT_ID": CHAT,
           "HERMES_SESSION_MESSAGE_ID": msg_id, "HERMES_SESSION_PLATFORM": "telegram"}
    cmd = ["hermes", "-p", "kura-kira", "-z", text, "-t", "duit"]
    if model:
        cmd += ["-m", model]
    t0 = time.time()
    out = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout)
    return (out.stdout.strip() or out.stderr.strip()[-500:]), time.time() - t0


def check(c: dict, led: Ledger, before_ids: set[int], reply: str, seeded: dict | None) -> list[str]:
    e = c["expect"]
    kind = e["kind"]
    today = led.today()
    rows = [r for r in led.conn.execute("SELECT id FROM entries WHERE deleted_at IS NULL")]
    new = [led.entry(r["id"]) for r in rows if r["id"] not in before_ids]
    fails = []

    if kind in ("ignore", "ask", "status"):
        if new:
            fails.append(f"logged {len(new)} entr{'y' if len(new) == 1 else 'ies'} but should not")
        if kind == "ignore" and reply and len(reply) > 2:
            fails.append(f"replied to chatter: {reply[:60]!r}")
        if kind in ("ask", "status") and not reply:
            fails.append("no reply")
        if kind == "status" and "RM" not in reply:
            fails.append("status reply has no numbers")
        return fails

    if kind == "fixed":
        for b in e["bills"]:
            row = led.conn.execute("SELECT paid_at FROM fixed_payments WHERE person=? AND bucket=? "
                                   "ORDER BY month DESC LIMIT 1", (e["person"], b)).fetchone()
            if not row or not row["paid_at"]:
                fails.append(f"{b} not marked paid")
        return fails + ([f"logged a spend: {new[0]['place']}"] if new else [])

    if kind == "settle":
        s = led.conn.execute("SELECT * FROM settlements").fetchall()
        if len(s) != 1:
            return [f"{len(s)} settle-ups recorded"]
        s = s[0]
        if (s["from_person"], s["to_person"], s["amount_sen"]) != (e["from"], e["to"], sen(e["amount"])):
            fails.append(f"settle {s['from_person']}→{s['to_person']} {s['amount_sen']}")
        return fails + ([f"logged a spend: {new[0]['place']}"] if new else [])

    if kind in ("answer", "deleted", "edited"):
        if seeded is None:
            return ["seed failed"]
        ent = led.entry(seeded["entry_id"])
        if new:
            fails.append(f"logged a new entry instead: {new[0]['place']}")
        if kind == "deleted":
            return fails + ([] if ent["deleted_at"] else ["entry not deleted"])
        if kind == "edited":
            return fails + ([] if ent["total_sen"] == sen(e["amount"]) else [f"amount {ent['total_sen']}"])
        target = ent
    else:  # spend
        if len(new) != 1:
            return [f"expected 1 new entry, got {len(new)}"]
        target = new[0]

    if "place" in e and not (norm(e["place"]) in norm(target["place"]) or norm(target["place"]) in norm(e["place"])):
        fails.append(f"place {target['place']!r}")
    if "amount" in e and target["total_sen"] != sen(e["amount"]):
        fails.append(f"amount {target['total_sen'] / 100:.2f}")
    if "shares" in e and target["shares"] != {k: sen(v) for k, v in e["shares"].items()}:
        fails.append(f"shares {target['shares']}")
    if "paid_by" in e and target["paid_by"] != e["paid_by"]:
        fails.append(f"paid_by {target['paid_by']}")
    if "bucket" in e:
        day = date.fromisoformat(target["spent_on"])
        want = daily_bucket(day) if e["bucket"] == "daily" else e["bucket"]
        if target["bucket"] != want:
            fails.append(f"bucket {target['bucket']} (want {want})")
    if "category" in e and (target["category"] or "").lower() != e["category"].lower():
        fails.append(f"category {target['category']}")
    if "date" in e and e["date"] == "yesterday" and target["spent_on"] != (today - timedelta(days=1)).isoformat():
        fails.append(f"date {target['spent_on']}")
    if "needs" in e and target["needs"] != e["needs"]:
        fails.append(f"needs {target['needs']}")
    if e.get("asked") and "?" not in reply:
        fails.append("should have asked a question")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", help="only cases whose id contains this")
    ap.add_argument("-m", "--model", help="override the profile's model")
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()

    cases_list = tomllib.loads((ROOT / "eval/cases.toml").read_text())["case"]
    cases = {c["id"]: c for c in cases_list}
    selected = [c for c in cases_list if not args.k or args.k in c["id"]]
    results = []
    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        cfg_path = eval_config(tmp)
        cfg = config.load(cfg_path)
        for i, c in enumerate(selected, 1):
            dbp = tmp / f"{c['id']}.db"
            env = {**os.environ, "DUIT_DB": str(dbp), "DUIT_CONFIG": str(cfg_path)}
            env.pop("PYTHONPATH", None)
            led = Ledger(db.connect(dbp), cfg)
            tools = Tools(led)
            seeded = seed(cases, c["after"], tools) if c.get("after") else None
            text = c["text"]
            if c.get("reply_to_bot") and seeded:
                quoted = seeded["reply"]
                if seeded.get("question"):
                    quoted = seeded["question"]["text"]
                text = f'[Replying to Kura-Kira: "{quoted}"]\n\n{text}'
            before = {r["id"] for r in led.conn.execute("SELECT id FROM entries")}
            try:
                reply, secs = run_agent(text, c["sender"], str(1000 + i), env, args.model, args.timeout)
            except subprocess.TimeoutExpired:
                reply, secs = "<timeout>", float(args.timeout)
            fails = check(c, led, before, reply, seeded)
            results.append({"id": c["id"], "ok": not fails, "fails": fails, "reply": reply, "secs": round(secs, 1)})
            print(f"{'PASS' if not fails else 'FAIL'}  {c['id']:<26} {secs:5.1f}s  {'; '.join(fails)}", flush=True)
            led.conn.close()

    passed = sum(r["ok"] for r in results)
    print(f"\n{passed}/{len(results)} passed")
    out = ROOT / "eval" / "results.json"
    out.write_text(json.dumps({"model": args.model, "date": date.today().isoformat(), "results": results},
                              indent=2, ensure_ascii=False))
    print(f"details: {out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

"""MCP server: the only tools the duit agent gets. Run with `python -m duit.server` (stdio).

Every write tool returns `reply` — the exact text to post in the group — so the model never has to
do arithmetic or format money itself. Bad input comes back as {"error": ..., "ask": ...} for the bot
to turn into a question instead of guessing.
"""

from __future__ import annotations

import functools
import threading
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import config, db, replies
from .config import DAILY
from .ledger import Ledger, LedgerError
from .periods import month_key

READ = ToolAnnotations(readOnlyHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)


def _instructions(cfg: config.Config) -> str:
    buckets = "\n".join(f"  - {k}: {b.label} ({b.kind}, RM{b.amount_sen / 100:g}/person)"
                        for k, b in cfg.buckets.items())
    people = ", ".join(f"{p.name} (telegram {p.telegram_id or 'unset'})" for p in cfg.people.values())
    return f"""Ledger for a couple's spending. People: {people}.
Budget buckets (pass the key):
  - {DAILY}: everyday spending; the ledger picks weekday/weekend from the date
{buckets}
Fixed bills (house, car) are not spends: use pay_fixed.
Categories (descriptive, for the table): {', '.join(cfg.categories)}.
Post the `reply` text from write tools as-is. When `question` is present, post its text and options,
then call record_question with the id of the message you sent."""


def build(cfg: config.Config | None = None, ledger: Ledger | None = None) -> MCPServer:
    cfg = cfg or config.load()
    led = ledger or Ledger(db.connect(), cfg)
    mcp = MCPServer("duit", instructions=_instructions(cfg), version="0.1.0")

    def person(value: str | int | None) -> str | None:
        """Accept a person key, display name or Telegram user ID."""
        if value is None or value == "":
            return None
        s = str(value).strip()
        if s.lstrip("-").isdigit():
            p = cfg.person_by_telegram(int(s))
            if p is None:
                raise LedgerError(f"Telegram user {s} is not one of us — ignore this message")
            return p.key
        return s

    lock = threading.Lock()  # one tool call at a time on the shared connection

    def guarded(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                with lock:
                    return fn(*args, **kwargs)
            except LedgerError as e:
                return {"error": str(e), "ask": True}
        return wrapper

    def spend_result(e: dict) -> dict:
        q = replies.question(cfg, e) if not e.get("duplicate") else None
        return {
            "entry_id": e["id"], "duplicate": e.get("duplicate", False),
            "reply": replies.spend_reply(cfg, e),
            "question": q,
            "ask_extra": e.get("ask_extra", False),
            "needs": e["needs"],
            "entry": {k: e[k] for k in ("place", "item", "category", "bucket", "total_sen", "shares", "paid_by",
                                        "spent_on")},
        }

    @mcp.tool(annotations=WRITE)
    @guarded
    def log_spend(sender: str, place: str, amount: float | str | None = None,
                  shares: dict[str, float | str] | None = None, paid_by: str | None = None,
                  bucket: str | None = None, category: str | None = None, item: str | None = None,
                  date: str | None = None, bucket_options: list[str] | None = None, raw_text: str | None = None,
                  chat_id: str | None = None, msg_id: str | None = None) -> dict:
        """Record one spend from the group chat.

        sender: who sent the message (Telegram user ID preferred, or name).
        place: where/what, as the user wrote it ("Sushi-Mentai", "Zapfan", "petrol").
        amount: total in RM. Omit when shares are given (total = sum of shares).
        shares: per-person RM amounts when the message splits it, e.g. {"hanz": 13.20, "vanisa": 14.50}.
                Omit for a normal message (all of it is the sender's).
        paid_by: who paid ("hanz", "vanisa", or "each" = each paid own). Omit if the message doesn't say;
                 the ledger assumes the sender when only the sender is involved, otherwise asks.
        bucket: "daily" for everyday spending, or a purpose bucket key (grocery, chuchu, petrol, toll,
                parents, extra). Omit if unsure — the entry goes to Unsorted and a question is returned;
                put the likely choices in bucket_options (e.g. ["daily", "extra"]).
        category: descriptive label (Food, Sport, Leisure, ...). item: optional detail ("lunch").
        date: YYYY-MM-DD, "today" or "yesterday" (default today).
        raw_text, chat_id, msg_id: the original message — msg_id makes retries safe (logged once).
        """
        e = led.log_spend(sender=person(sender), place=place, total=amount,
                          shares={person(k): v for k, v in shares.items()} if shares else None,
                          paid_by=paid_by if paid_by in (None, "each") else person(paid_by),
                          bucket=bucket, category=category, item=item, spent_on=date,
                          bucket_options=bucket_options, raw_text=raw_text, chat_id=chat_id, msg_id=msg_id)
        return spend_result(e)

    @mcp.tool(annotations=WRITE)
    @guarded
    def answer(entry_id: int | None = None, reply_to_msg_id: str | None = None, bucket: str | None = None,
               category: str | None = None, paid_by: str | None = None) -> dict:
        """Apply an answer to a question the bot asked (who paid / which bucket).

        Identify the entry by entry_id, or by reply_to_msg_id (the message the user replied to — either
        the original spend or the bot's question). The answer is remembered for that place.
        """
        if entry_id is None:
            if reply_to_msg_id is None:
                pend = led.pending()
                if len(pend) != 1:
                    raise LedgerError(f"{len(pend)} entries are waiting — which one? (reply to the question)")
                entry_id = pend[0]["id"]
            else:
                found = led.find_by_message(reply_to_msg_id)
                if found is None:
                    raise LedgerError("that message isn't a logged spend or one of my questions")
                entry_id = found["id"]
        e = led.resolve(entry_id, bucket=bucket, category=category,
                        paid_by=paid_by if paid_by in (None, "each") else person(paid_by))
        return spend_result(e)

    @mcp.tool(annotations=WRITE)
    @guarded
    def record_question(entry_id: int, question_msg_id: str) -> dict:
        """Remember which chat message asked about an entry, so replies to it find the entry."""
        led.set_question(entry_id, question_msg_id)
        return {"ok": True}

    @mcp.tool(annotations=WRITE)
    @guarded
    def edit_spend(entry_id: int, place: str | None = None, item: str | None = None,
                   amount: float | str | None = None, shares: dict[str, float | str] | None = None,
                   paid_by: str | None = None, bucket: str | None = None, category: str | None = None,
                   date: str | None = None) -> dict:
        """Fix a logged spend ("edit #142 food 30", "wrong, 26.20"). Only pass what changes."""
        e = led.edit(entry_id, place=place, item=item, total=amount,
                     shares={person(k): v for k, v in shares.items()} if shares else None,
                     paid_by=paid_by if paid_by in (None, "each") else person(paid_by),
                     bucket=bucket, category=category, spent_on=date)
        return spend_result(e)

    @mcp.tool(annotations=WRITE)
    @guarded
    def delete_spend(entry_id: int | None = None, sender: str | None = None) -> dict:
        """Delete a spend: by entry_id ("delete #142"), or the sender's latest one ("undo")."""
        if entry_id is None:
            if sender is None:
                raise LedgerError("say which entry, or who is undoing")
            e = led.undo(person(sender))
        else:
            e = led.delete(entry_id)
        return {"entry_id": e["id"], "reply": f"🗑️ Deleted #{e['id']} {e['place']} "
                                              f"{replies.fmt(e['total_sen'], cfg.currency)}"}

    @mcp.tool(annotations=WRITE)
    @guarded
    def settle_up(from_person: str, to_person: str, amount: float | str | None = None,
                  raw_text: str | None = None, chat_id: str | None = None, msg_id: str | None = None) -> dict:
        """Money paid back between the two ("vanisa paid hanz 86.30"). Omit amount to clear the whole balance.
        Never counts as spending."""
        r = led.settle(from_person=person(from_person), to_person=person(to_person), amount=amount,
                       raw_text=raw_text, chat_id=chat_id, msg_id=msg_id)
        if r["duplicate"]:
            return {"reply": "Already recorded.", **r}
        text = (f"🤝 {cfg.people[r['from']].name} → {cfg.people[r['to']].name} "
                f"{replies.fmt(r['amount'], cfg.currency)}\n{replies.balance_line(cfg, r['balance'])}")
        return {"reply": text, **r}

    @mcp.tool(annotations=WRITE)
    @guarded
    def pay_fixed(person_name: str, bill: str, month: str | None = None) -> dict:
        """Mark a fixed bill paid ("house paid", "car paid"). bill: house or car. month: YYYY-MM (default now)."""
        r = led.pay_fixed(person(person_name), bill, month)
        return {"reply": replies.fixed_reply(cfg, r), **r}

    @mcp.tool(annotations=WRITE)
    @guarded
    def set_plan(bucket: str, amount: float | str, person_name: str | None = None,
                 month: str | None = None) -> dict:
        """Change a monthly budget ("plan: grocery 250"). person_name omitted = both. Applies from `month`
        (default this month) and is copied into later months."""
        r = led.set_plan(bucket, amount, person(person_name), month)
        names = " & ".join(cfg.people[p].name for p in r["people"])
        return {"reply": f"📝 {cfg.buckets[r['bucket']].label} = {replies.fmt(r['amount'], cfg.currency)} "
                         f"for {names} from {r['month']}", **r}

    @mcp.tool(annotations=READ)
    @guarded
    def lookup_place(name: str) -> dict:
        """What the ledger has learned about a place (bucket/category), or null if it's new."""
        return {"place": led.lookup_place(name)}

    @mcp.tool(annotations=READ)
    @guarded
    def status(month: str | None = None, person_name: str | None = None) -> dict:
        """Budget status ("how are we doing?", "how much left?"). Returns `reply` text plus the numbers."""
        st = led.status(month)
        p = person(person_name)
        return {"reply": replies.status_text(cfg, st, cfg.person(p).key if p else None), "status": st}

    @mcp.tool(annotations=READ)
    @guarded
    def list_spends(month: str | None = None, person_name: str | None = None, bucket: str | None = None,
                    category: str | None = None, paid_by: str | None = None, query: str | None = None,
                    limit: int = 30) -> dict:
        """Search logged spends (by month YYYY-MM, person, bucket, category, payer, or text)."""
        rows = led.list_entries(month or month_key(led.today()), person(person_name), bucket, category,
                                paid_by if paid_by in (None, "each") else person(paid_by), query)
        keep = ("id", "spent_on", "place", "item", "category", "bucket", "total_sen", "shares", "paid_by", "needs")
        return {"count": len(rows), "entries": [{k: r[k] for k in keep} for r in rows[:limit]]}

    @mcp.tool(annotations=READ)
    @guarded
    def pending() -> dict:
        """Entries still waiting for an answer, with the question to (re)ask for each."""
        items = []
        for p in led.pending():
            e = led.entry(p["id"])
            items.append({**p, "question": replies.question(cfg, e)})
        return {"count": len(items), "pending": items}

    @mcp.tool(annotations=READ)
    @guarded
    def fixed_due(month: str | None = None) -> dict:
        """Fixed bills not yet paid this month (for reminders)."""
        rows = led.fixed_due(month)
        return {"due": rows, "reply": "\n".join(
            f"⏳ @{cfg.people[r['person']].name} {cfg.buckets[r['bucket']].label} "
            f"{replies.fmt(r['amount_sen'], cfg.currency)} is due" for r in rows) or "All fixed bills paid ✓"}

    return mcp


def tool_names(server: MCPServer) -> list[str]:
    return [t.name for t in server._tool_manager.list_tools()]


def main(argv: Any = None) -> None:
    build().run("stdio")


if __name__ == "__main__":
    main()

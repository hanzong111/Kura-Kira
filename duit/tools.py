"""The agent's tools: one spec list + one dispatcher, used by the Hermes plugin and the tests.

Who sent the message, the chat and the message id come from the gateway (`Context`), never from
the model, so the model can't book a spend to the wrong person. Every write returns `reply`, the
exact text to post. Bad input returns {"error", "ask": true} so the bot asks instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from . import replies
from .config import DAILY, Config
from .ledger import Ledger, LedgerError
from .money import fmt
from .periods import month_key


@dataclass(frozen=True)
class Context:
    """Facts about the incoming message, supplied by the gateway."""
    sender_telegram_id: str = ""
    chat_id: str = ""
    msg_id: str = ""
    sender: str | None = None  # person key; only for tests / CLI use without Telegram IDs


def _s(desc: str, **extra) -> dict:
    return {"type": "string", "description": desc, **extra}


_AMOUNT = {"type": ["number", "string"], "description": "RM amount, e.g. 56.50 or \"RM56.50\""}
_SHARES = {"type": "object", "additionalProperties": {"type": ["number", "string"]},
           "description": "Per-person RM amounts when the message splits it, e.g. {\"hanz\": 13.20, \"vanisa\": 14.50}. "
                          "Omit for a normal message (all of it is the sender's)."}
_PERSON = _s("hanz or vanisa")
_ENTRY = {"type": "integer", "description": "Entry number (the #123 in the bot's messages)"}
_MONTH = _s("YYYY-MM; default this month")


def specs(cfg: Config) -> list[dict]:
    purpose = [k for k, b in cfg.buckets.items() if b.kind == "monthly"]
    bucket_desc = (f"'{DAILY}' = everyday spending (the ledger picks weekday/weekend from the date), or a purpose "
                   f"bucket: {', '.join(purpose)}. Omit when unsure.")
    cats = ", ".join(cfg.categories)
    return [
        {"name": "duit_log_spend",
         "description": "Record a spend from the group chat. The sender, chat and message are filled in automatically.",
         "parameters": {"type": "object", "required": ["place"], "properties": {
             "place": _s("Where/what as the user wrote it: 'Sushi-Mentai', 'Zapfan', 'petrol'"),
             "amount": {**_AMOUNT, "description": "Total in RM. Omit when shares are given (total = sum of shares)."},
             "shares": _SHARES,
             "paid_by": _s("Who paid, only if the message says: hanz, vanisa, or each (each paid own). Omit otherwise."),
             "bucket": _s(bucket_desc),
             "bucket_options": {"type": "array", "items": {"type": "string"},
                                "description": "When bucket is omitted because you're unsure: the 2-3 likely bucket keys."},
             "category": _s(f"One of: {cats}"),
             "item": _s("Optional detail, e.g. 'lunch'"),
             "date": _s("YYYY-MM-DD, 'today' or 'yesterday'. Default today."),
             "part": {"type": "integer", "description": "When one message has several spends: 1, 2, 3... for each. Default 1."},
             "raw_text": _s("The message text as sent"),
         }}},
        {"name": "duit_answer",
         "description": "Apply an answer to the bot's question about an entry (who paid / which bucket). The answer is "
                        "remembered for that place.",
         "parameters": {"type": "object", "properties": {
             "entry_id": {**_ENTRY, "description": "The #number from the question being replied to. Omit if the user "
                                                   "didn't reply to a message (works when only one entry is waiting)."},
             "bucket": _s(bucket_desc), "category": _s(f"One of: {cats}"),
             "paid_by": _s("hanz, vanisa, or each"),
         }}},
        {"name": "duit_edit_spend",
         "description": "Fix a logged spend ('edit #142 food 30', 'wrong, should be 85'). Pass only what changes.",
         "parameters": {"type": "object", "properties": {
             "entry_id": {**_ENTRY, "description": "Entry to fix. Omit = the sender's latest entry."},
             "place": _s("New place"), "item": _s("New item"), "amount": _AMOUNT, "shares": _SHARES,
             "paid_by": _s("hanz, vanisa, or each"), "bucket": _s(bucket_desc), "category": _s(f"One of: {cats}"),
             "date": _s("YYYY-MM-DD, 'today' or 'yesterday'"),
         }}},
        {"name": "duit_delete_spend",
         "description": "Delete a spend: 'delete #142', or 'undo' (omit entry_id = the sender's latest entry).",
         "parameters": {"type": "object", "properties": {"entry_id": _ENTRY}}},
        {"name": "duit_settle_up",
         "description": "Money paid back between the two ('vanisa paid hanz 86.30', 'settled'). Never counts as "
                        "spending. Omit amount to clear the whole balance.",
         "parameters": {"type": "object", "required": ["from_person", "to_person"], "properties": {
             "from_person": _PERSON, "to_person": _PERSON, "amount": _AMOUNT}}},
        {"name": "duit_pay_fixed",
         "description": "Mark fixed bills paid ('house paid', 'house + car paid'). Defaults to the sender.",
         "parameters": {"type": "object", "required": ["bills"], "properties": {
             "bills": {"type": "array", "items": {"type": "string", "enum": [k for k, b in cfg.buckets.items()
                                                                            if b.kind == "fixed"]}},
             "person": {**_PERSON, "description": "Only if paying for someone else. Default the sender."},
             "month": _MONTH}}},
        {"name": "duit_set_plan",
         "description": "Change a budget ('plan: grocery 250', 'vanisa petrol 150', 'weekend 250'). Weekday/weekend "
                        "amounts are per week; the others per month. Copied into later months.",
         "parameters": {"type": "object", "required": ["bucket", "amount"], "properties": {
             "bucket": _s(f"Bucket key: {', '.join(cfg.buckets)}"), "amount": _AMOUNT,
             "person": {**_PERSON, "description": "Omit = both"}, "month": _MONTH}}},
        {"name": "duit_status",
         "description": "Budget status ('how are we doing?', 'how much left?'). Post the returned reply.",
         "parameters": {"type": "object", "properties": {
             "month": _MONTH,
             "person": {**_PERSON, "description": "Only this person; use 'me' for the sender. Omit = both."}}}},
        {"name": "duit_list_spends",
         "description": "Search logged spends ('what did we spend on food this month?').",
         "parameters": {"type": "object", "properties": {
             "month": _MONTH, "person": _PERSON, "bucket": _s("Bucket key or 'unsorted'"),
             "category": _s("Category"), "paid_by": _s("hanz, vanisa or each"), "query": _s("Text to find"),
             "limit": {"type": "integer", "description": "Max rows, default 30"}}}},
        {"name": "duit_pending",
         "description": "Entries still waiting for an answer, with the question to re-ask for each.",
         "parameters": {"type": "object", "properties": {}}},
        {"name": "duit_lookup_place",
         "description": "What the ledger learned about a place (bucket/category), or null if new.",
         "parameters": {"type": "object", "required": ["name"], "properties": {"name": _s("Place name")}}},
        {"name": "duit_fixed_due",
         "description": "Fixed bills not paid yet this month (for reminders).",
         "parameters": {"type": "object", "properties": {"month": _MONTH}}},
    ]


class Tools:
    def __init__(self, ledger: Ledger):
        self.led = ledger
        self.cfg = ledger.cfg
        self._handlers: dict[str, Callable[[dict, Context], dict]] = {
            "duit_log_spend": self.log_spend, "duit_answer": self.answer, "duit_edit_spend": self.edit_spend,
            "duit_delete_spend": self.delete_spend, "duit_settle_up": self.settle_up,
            "duit_pay_fixed": self.pay_fixed, "duit_set_plan": self.set_plan, "duit_status": self.status,
            "duit_list_spends": self.list_spends, "duit_pending": self.pending,
            "duit_lookup_place": self.lookup_place, "duit_fixed_due": self.fixed_due,
        }

    def call(self, name: str, args: dict | None, ctx: Context) -> dict:
        handler = self._handlers.get(name)
        if handler is None:
            return {"error": f"unknown tool {name}"}
        try:
            return handler(dict(args or {}), ctx)
        except LedgerError as e:
            return {"error": str(e), "ask": True}

    # ---- identity ---------------------------------------------------------------------------------
    def _sender(self, ctx: Context) -> str:
        if ctx.sender_telegram_id:
            try:
                p = self.cfg.person_by_telegram(int(ctx.sender_telegram_id))
            except ValueError:
                p = None
            if p is None:
                raise LedgerError("this message isn't from Hanz or Vanisa — ignore it and don't reply")
            return p.key
        if ctx.sender:
            return self.cfg.person(ctx.sender).key
        raise LedgerError("I can't tell who sent this message")

    def _person(self, value: Any, ctx: Context) -> str | None:
        if value in (None, ""):
            return None
        v = str(value).strip().lower()
        if v in ("me", "i", "myself"):
            return self._sender(ctx)
        if v in ("each", "each paid own", "own"):
            return "each"
        try:
            return self.cfg.person(v).key
        except ValueError as e:
            raise LedgerError(str(e)) from None

    def _shares(self, shares: dict | None, ctx: Context) -> dict | None:
        if not shares:
            return None
        out = {}
        for k, v in shares.items():
            p = self._person(k, ctx)
            if p in (None, "each"):
                raise LedgerError(f"shares must be per person, got {k!r}")
            out[p] = v
        return out

    def _spend_result(self, e: dict) -> dict:
        q = None if e.get("duplicate") else replies.question(self.cfg, e)
        return {"entry_id": e["id"], "duplicate": e.get("duplicate", False),
                "reply": replies.spend_reply(self.cfg, e), "question": q,
                "ask_extra": bool(e.get("ask_extra")) and q is None, "needs": e["needs"]}

    def _latest(self, ctx: Context) -> int:
        rows = self.led.conn.execute("SELECT id FROM entries WHERE sender=? AND deleted_at IS NULL "
                                     "ORDER BY id DESC LIMIT 1", (self._sender(ctx),)).fetchone()
        if rows is None:
            raise LedgerError("you have no entries yet")
        return rows["id"]

    # ---- handlers ---------------------------------------------------------------------------------
    def log_spend(self, a: dict, ctx: Context) -> dict:
        part = int(a.get("part") or 1)
        msg_id = None
        if ctx.msg_id:
            msg_id = ctx.msg_id if part == 1 else f"{ctx.msg_id}:{part}"
        e = self.led.log_spend(
            sender=self._sender(ctx), place=a.get("place", ""), total=a.get("amount"),
            shares=self._shares(a.get("shares"), ctx), paid_by=self._person(a.get("paid_by"), ctx),
            bucket=a.get("bucket") or None, category=a.get("category") or None, item=a.get("item") or None,
            spent_on=a.get("date") or None, bucket_options=a.get("bucket_options") or None,
            raw_text=a.get("raw_text"), chat_id=ctx.chat_id or None, msg_id=msg_id)
        return self._spend_result(e)

    def _not_own_question(self, entry_id: int, ctx: Context) -> None:
        """An answer must come from a later message than the spend: the bot can't answer its own question."""
        e = self.led.entry(entry_id)
        if ctx.msg_id and e["msg_id"] and e["chat_id"] == (ctx.chat_id or None) and \
                e["msg_id"].split(":")[0] == ctx.msg_id and e["needs"]:
            raise LedgerError(f"#{entry_id} is waiting for their answer — post the question and wait; "
                              "don't answer it yourself")

    def answer(self, a: dict, ctx: Context) -> dict:
        entry_id = a.get("entry_id")
        if entry_id is None:
            pend = self.led.pending()
            if len(pend) != 1:
                ids = ", ".join(f"#{p['id']} {p['place']}" for p in pend) or "none"
                raise LedgerError(f"{len(pend)} entries are waiting ({ids}) — ask them to reply to the question")
            entry_id = pend[0]["id"]
        self._not_own_question(int(entry_id), ctx)
        e = self.led.resolve(int(entry_id), bucket=a.get("bucket") or None, category=a.get("category") or None,
                             paid_by=self._person(a.get("paid_by"), ctx))
        return self._spend_result(e)

    def edit_spend(self, a: dict, ctx: Context) -> dict:
        entry_id = int(a["entry_id"]) if a.get("entry_id") is not None else self._latest(ctx)
        if a.get("paid_by") or a.get("bucket"):
            self._not_own_question(entry_id, ctx)
        e = self.led.edit(entry_id, place=a.get("place"), item=a.get("item"), total=a.get("amount"),
                          shares=self._shares(a.get("shares"), ctx), paid_by=self._person(a.get("paid_by"), ctx),
                          bucket=a.get("bucket"), category=a.get("category"), spent_on=a.get("date"))
        r = self._spend_result(e)
        r["reply"] = "✏️ " + r["reply"].removeprefix("✅ ")
        return r

    def delete_spend(self, a: dict, ctx: Context) -> dict:
        entry_id = int(a["entry_id"]) if a.get("entry_id") is not None else self._latest(ctx)
        e = self.led.delete(entry_id)
        return {"entry_id": e["id"], "reply": f"🗑️ Deleted #{e['id']} {e['place']} {fmt(e['total_sen'], self.cfg.currency)}"}

    def settle_up(self, a: dict, ctx: Context) -> dict:
        r = self.led.settle(from_person=self._person(a.get("from_person"), ctx),
                            to_person=self._person(a.get("to_person"), ctx), amount=a.get("amount"),
                            chat_id=ctx.chat_id or None, msg_id=ctx.msg_id or None)
        if r["duplicate"]:
            return {"reply": "Already recorded."}
        names = self.cfg.people
        return {"reply": f"🤝 {names[r['from']].name} → {names[r['to']].name} {fmt(r['amount'], self.cfg.currency)}\n"
                         f"{replies.balance_line(self.cfg, r['balance'])}"}

    def pay_fixed(self, a: dict, ctx: Context) -> dict:
        person = self._person(a.get("person"), ctx) or self._sender(ctx)
        bills = a.get("bills") or []
        if not bills:
            raise LedgerError("which bill — house or car?")
        lines = [replies.fixed_reply(self.cfg, self.led.pay_fixed(person, b, a.get("month"))) for b in bills]
        return {"reply": "\n".join(lines)}

    def set_plan(self, a: dict, ctx: Context) -> dict:
        r = self.led.set_plan(a.get("bucket", ""), a.get("amount"), self._person(a.get("person"), ctx), a.get("month"))
        names = " & ".join(self.cfg.people[p].name for p in r["people"])
        return {"reply": f"📝 {self.cfg.buckets[r['bucket']].label} = {fmt(r['amount'], self.cfg.currency)} "
                         f"for {names} from {r['month']}"}

    def status(self, a: dict, ctx: Context) -> dict:
        st = self.led.status(a.get("month"))
        return {"reply": replies.status_text(self.cfg, st, self._person(a.get("person"), ctx))}

    def list_spends(self, a: dict, ctx: Context) -> dict:
        rows = self.led.list_entries(a.get("month") or month_key(self.led.today()), self._person(a.get("person"), ctx),
                                     a.get("bucket"), a.get("category"), self._person(a.get("paid_by"), ctx),
                                     a.get("query"))
        c = self.cfg.currency
        limit = int(a.get("limit") or 30)
        lines = [f"#{r['id']} {r['spent_on']} {r['place']} {fmt(r['total_sen'], c)} "
                 f"[{self.cfg.buckets[r['bucket']].label if r['bucket'] else 'Unsorted'}"
                 f"{' · ' + r['category'] if r['category'] else ''}] "
                 + " · ".join(f"{self.cfg.people[p].name} {fmt(v, c)}" for p, v in r["shares"].items())
                 for r in rows[:limit]]
        person = self._person(a.get("person"), ctx)
        total = sum(r["shares"].get(person, 0) if person else r["total_sen"] for r in rows)
        return {"count": len(rows), "total": fmt(total, c), "entries": lines}

    def pending(self, a: dict, ctx: Context) -> dict:
        items = [replies.question(self.cfg, self.led.entry(p["id"])) for p in self.led.pending()]
        return {"count": len(items), "pending": items}

    def lookup_place(self, a: dict, ctx: Context) -> dict:
        return {"place": self.led.lookup_place(a.get("name", ""))}

    def fixed_due(self, a: dict, ctx: Context) -> dict:
        rows = self.led.fixed_due(a.get("month"))
        return {"count": len(rows), "reply": "\n".join(
            f"⏳ @{self.cfg.people[r['person']].name} {self.cfg.buckets[r['bucket']].label} "
            f"{fmt(r['amount_sen'], self.cfg.currency)} is due" for r in rows) or "All fixed bills paid ✓"}

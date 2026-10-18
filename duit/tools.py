"""The agent's tools: one spec list + one dispatcher, used by the Hermes plugin and the tests.

Division of labour: the model only *reads* the message (place, category, bucket, who, how it was
split). Everything numeric is code:
- the sender, chat, message id, message text and send time come from the gateway (`Context`);
- every amount the model passes must appear in the original message (`textcheck`);
- splits ("even", "2:1", "for vanisa") are computed here, never by the model;
- dates ("yesterday") are relative to when the message was sent, not when it was processed;
- every tool returns `reply`, the exact text to post (the plugin enforces that it's what gets posted);
- every call is written to the audit table.
Bad input returns {"error", "ask": true} so the bot asks instead of guessing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable

from . import catalogue, replies, textcheck
from .config import DAILY, Config
from .ledger import Ledger, LedgerError
from .money import fmt, parse_amount, split_even, split_ratio
from .periods import month_key

# when the model leaves out the bucket (and offers no options), the category decides
CATEGORY_BUCKET = {"groceries": "grocery", "pet": "chuchu", "toiletries": "chuchu", "family": "parents"}


@dataclass(frozen=True)
class Context:
    """Facts about the incoming message, supplied by the gateway — never by the model."""
    sender_telegram_id: str = ""
    chat_id: str = ""
    msg_id: str = ""
    text: str | None = None         # the message as sent (None = unknown: amount checks are skipped)
    sent_at: datetime | None = None  # when it was sent (None = now)
    sender: str | None = None        # person key; only for tests / CLI use without Telegram IDs


def _rm(sen: int) -> str:
    """Sen -> exact decimal string for the ledger (no floats anywhere)."""
    return f"{sen // 100}.{sen % 100:02d}"


def _s(desc: str, **extra) -> dict:
    return {"type": "string", "description": desc, **extra}


_AMOUNT = {"type": ["number", "string"],
           "description": "RM amount exactly as written in the message, e.g. \"RM56.50\" or \"12.9\". Never compute it."}
_SHARES = {"type": "object", "additionalProperties": {"type": ["number", "string"]},
           "description": "Only when the message itself states each person's amount, e.g. \"13.20 hanz, 14.50 vanisa\" "
                          "→ {\"hanz\": \"13.20\", \"vanisa\": \"14.50\"}. Never compute shares; use `split` instead."}
_PERSON = _s("hanz or vanisa")
_ENTRY = {"type": "integer", "description": "Entry number (the #123 in the bot's messages)"}
_MONTH = _s("YYYY-MM; default this month")


def specs(cfg: Config) -> list[dict]:
    purpose = [k for k, b in cfg.buckets.items() if b.kind == "monthly"]
    bucket_desc = (f"'{DAILY}' = everyday spending (weekday/weekend is picked from the date), or a purpose bucket: "
                   f"{', '.join(purpose)}. Omit when unsure.")
    cats = ", ".join(cfg.categories)
    split_props = {
        "split": _s("How a shared spend is divided, when the message says so: \"even\" (split / shared / half) or a "
                    "ratio like \"2:1\" in the order of split_between. The ledger computes the shares."),
        "split_between": {"type": "array", "items": {"type": "string"},
                          "description": "People in the split, in ratio order. Default both: [\"hanz\", \"vanisa\"]."},
        "for_person": _s("When the whole spend is someone else's (\"grab 25 for vanisa\"): that person."),
    }
    return [
        {"name": "duit_log_spend",
         "description": "Record a spend from the group chat. Sender, chat, message, text and date are filled in "
                        "automatically; amounts are checked against the message.",
         "parameters": {"type": "object", "required": ["place"], "properties": {
             "place": _s("Where/what as the user wrote it: 'Sushi-Mentai', 'Zapfan', 'petrol'"),
             "amount": {**_AMOUNT, "description": _AMOUNT["description"] + " Omit only when `shares` are given."},
             "shares": _SHARES, **split_props,
             "paid_by": _s("Who paid, only if the message says: hanz, vanisa, or each (each paid own). Omit otherwise."),
             "bucket": _s(bucket_desc),
             "bucket_options": {"type": "array", "items": {"type": "string"},
                                "description": "When bucket is omitted because you're unsure: the 2-3 likely bucket keys."},
             "category": _s(f"One of: {cats}"),
             "item": _s("Optional detail, e.g. 'lunch'"),
             "date": _s("Only if the message says: 'yesterday' or YYYY-MM-DD. Default: when it was sent."),
             "part": {"type": "integer", "description": "When one message has several spends: 1, 2, 3... for each. Default 1."},
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
         "description": "Fix a logged spend ('edit #142 food 30', 'wrong, should be 85'). Pass only what changes; "
                        "a new amount must appear in the message.",
         "parameters": {"type": "object", "properties": {
             "entry_id": {**_ENTRY, "description": "Entry to fix. Omit = the sender's latest entry."},
             "place": _s("New place"), "item": _s("New item"), "amount": _AMOUNT, "shares": _SHARES, **split_props,
             "paid_by": _s("hanz, vanisa, or each"), "bucket": _s(bucket_desc), "category": _s(f"One of: {cats}"),
             "date": _s("'yesterday' or YYYY-MM-DD"),
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
         "description": "Mark fixed bills paid ('house paid', 'house + car paid'). Defaults to the sender. Bills: " +
                        ", ".join(f"{k} = {b.label}" for k, b in cfg.buckets.items() if b.kind == "fixed") + ".",
         "parameters": {"type": "object", "required": ["bills"], "properties": {
             "bills": {"type": "array", "items": {"type": "string", "enum": [k for k, b in cfg.buckets.items()
                                                                            if b.kind == "fixed"]}},
             "person": {**_PERSON, "description": "Only if paying for someone else. Default the sender."},
             "month": _MONTH}}},
        {"name": "duit_set_plan",
         "description": "Change a budget ('plan: grocery 250', 'vanisa petrol 150', 'weekday 25 a day'). Weekday/weekend "
                        "amounts are per day; the others per month. Copied into later months.",
         "parameters": {"type": "object", "required": ["bucket", "amount"], "properties": {
             "bucket": _s(f"Bucket key: {', '.join(cfg.buckets)}"), "amount": _AMOUNT,
             "person": {**_PERSON, "description": "Omit = both"}, "month": _MONTH}}},
        {"name": "duit_status",
         "description": "Budget status ('how are we doing?', 'how much left?', 'how much left for weekend?').",
         "parameters": {"type": "object", "properties": {
             "month": _MONTH,
             "person": {**_PERSON, "description": "Only this person; 'me' for the sender. Omit = both."},
             "bucket": _s("Only this bucket (e.g. 'weekend' for 'how much left for weekend?')")}}},
        {"name": "duit_list_spends",
         "description": "Search logged spends ('what did we spend on food this month?'). Returns the total too.",
         "parameters": {"type": "object", "properties": {
             "month": _MONTH, "person": _PERSON, "bucket": _s("Bucket key or 'unsorted'"),
             "category": _s("Category"), "paid_by": _s("hanz, vanisa or each"), "query": _s("Text to find"),
             "limit": {"type": "integer", "description": "Max rows shown, default 15"}}}},
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


def chat_lines(result: dict) -> list[str]:
    """What a tool result contributes to the group message (empty for errors: the bot asks instead)."""
    if result.get("error"):
        return []
    lines = [result["reply"]] if result.get("reply") else []
    q = result.get("question")
    if q:
        lines.append(q["text"])
    elif result.get("ask_extra"):
        lines.append(f"Everyday or Extra? (#{result['entry_id']})")
    return lines


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
        args = dict(args or {})
        if handler is None:
            result = {"error": f"unknown tool {name}"}
        else:
            try:
                result = handler(args, ctx)
            except LedgerError as e:
                result = {"error": str(e), "ask": True}
        self._audit(name, args, ctx, result)
        return result

    def _audit(self, name: str, args: dict, ctx: Context, result: dict) -> None:
        try:
            self.led.conn.execute(
                "INSERT INTO audit(at, tool, sender, chat_id, msg_id, args, result, ok) VALUES (?,?,?,?,?,?,?,?)",
                (self.led.now().isoformat(timespec="seconds"), name, ctx.sender_telegram_id or ctx.sender,
                 ctx.chat_id or None, ctx.msg_id or None, json.dumps(args, ensure_ascii=False, default=str),
                 json.dumps(result, ensure_ascii=False, default=str), int(not result.get("error"))))
        except Exception:  # auditing must never break bookkeeping
            pass

    # ---- identity, dates, amounts -----------------------------------------------------------------
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

    def _sent_day(self, ctx: Context) -> date:
        if ctx.sent_at is None:
            return self.led.today()
        return ctx.sent_at.astimezone(self.cfg.tz).date()

    def _day(self, value: Any, ctx: Context) -> date:
        """The spend date: from the message ('yesterday' = the day before it was sent), default the send day."""
        sent = self._sent_day(ctx)
        if value in (None, "", "today"):
            return sent
        v = str(value).strip().lower()
        if v == "yesterday":
            return sent - timedelta(days=1)
        try:
            return date.fromisoformat(v)
        except ValueError:
            raise LedgerError(f"date must be 'yesterday' or YYYY-MM-DD, got {value!r}") from None

    @staticmethod
    def _sen(value: Any, what: str) -> int:
        try:
            sen = parse_amount(value)
        except ValueError:
            raise LedgerError(f"{what} {value!r} isn't an amount") from None
        if sen <= 0:
            raise LedgerError(f"{what} must be more than zero")
        return sen

    def _verify(self, ctx: Context, amounts: dict[str, int]) -> None:
        problem = textcheck.check_amounts(ctx.text, amounts)
        if problem:
            raise LedgerError(problem)

    def _amounts(self, a: dict, ctx: Context, sender: str, required: bool) -> tuple[int | None, dict | None]:
        """Turn what the model read (amount + split / for_person / stated shares) into a total and shares.
        All arithmetic happens here; every number the model passed must appear in the message."""
        stated = a.get("shares") or None
        split = (a.get("split") or "").strip().lower() or None
        for_person = self._person(a.get("for_person"), ctx)
        modes = sum(bool(x) for x in (stated, split, for_person))
        if modes > 1:
            raise LedgerError("use only one of shares / split / for_person")
        total = self._sen(a["amount"], "amount") if a.get("amount") not in (None, "") else None

        if stated:
            shares = {}
            for k, v in stated.items():
                p = self._person(k, ctx)
                if p in (None, "each"):
                    raise LedgerError(f"shares must be per person, got {k!r}")
                shares[p] = self._sen(v, f"{self.cfg.people[p].name}'s share")
            checks = {f"{self.cfg.people[p].name}'s share": v for p, v in shares.items()}
            if total is not None:
                checks["total"] = total
            self._verify(ctx, checks)
            if total is None:
                extra = [n for n in textcheck.unused_numbers(ctx.text, list(shares.values())) if n > max(shares.values())]
                if extra:
                    raise LedgerError(f"the message also says {extra[0] / 100:.2f} — is that the total? The shares add "
                                      f"up to {sum(shares.values()) / 100:.2f}. Ask which is right")
            return total, shares

        if total is None:
            if required:
                raise LedgerError("amount is missing — ask how much")
            return None, None
        self._verify(ctx, {"total": total})

        if split:
            people = [self._person(p, ctx) for p in (a.get("split_between") or list(self.cfg.people))]
            if any(p in (None, "each") for p in people) or len(set(people)) != len(people) or len(people) < 2:
                raise LedgerError("split_between must list two or more different people")
            if split in ("even", "half", "equal", "shared", "50/50", "50:50"):
                parts = split_even(total, len(people))
            else:
                try:
                    ratio = [float(x) for x in split.replace("/", ":").split(":")]
                except ValueError:
                    raise LedgerError(f"split must be 'even' or a ratio like '2:1', got {split!r}") from None
                if len(ratio) != len(people):
                    raise LedgerError(f"ratio {split} has {len(ratio)} parts but {len(people)} people")
                parts = split_ratio(total, ratio)
            return total, dict(zip(people, parts))
        if for_person:
            return total, {for_person: total}
        return total, {sender: total}

    def _fixed_bill(self, a: dict):
        """A fixed bill (house, car, an installment) sent as a spend: named as the bucket, or the place/item is
        the bill's whole name ("mopping machine", "house"; not "car wash")."""
        named = (a.get("bucket") or "").strip().lower()
        for b in self.cfg.buckets.values():
            if b.kind == "fixed" and named in (b.key, b.label.lower()):
                return b
        return self.cfg.fixed_bill_named(a.get("place")) or self.cfg.fixed_bill_named(a.get("item"))

    def _fixed_from_classify(self, a: dict):
        """The place is known (learned / catalogue / category) as a fixed bill, e.g. "parents 500"."""
        bucket, _, source = self._classify(a)
        if source == "learned":
            bucket = (self.led.lookup_place(a.get("place", "")) or {}).get("bucket")
        b = self.cfg.buckets.get(bucket or "")
        return b if b and b.kind == "fixed" else None

    def _pay_bill_instead(self, bill, a: dict, ctx: Context, person: str) -> dict:
        """Bills are never spends (they'd eat the weekday/weekend budget): mark the bill paid instead."""
        if a.get("amount") not in (None, ""):
            self._verify(ctx, {"total": self._sen(a["amount"], "amount")})
        r = self.led.pay_fixed(person, bill.key, a.get("month") or month_key(self._sent_day(ctx)))
        line = replies.fixed_reply(self.cfg, r)
        if a.get("amount") not in (None, "") and self._sen(a["amount"], "amount") != r["amount"]:
            line += f" (the bill is set at {fmt(r['amount'], self.cfg.currency)})"
        return {"reply": line, "question": None, "fixed": bill.key}

    def _keep_out_of_daily(self, bucket: str | None, a: dict) -> str | None:
        """Chu Chu / toiletries never count as weekday/weekend, whatever the model said: the category, the
        places the couple taught the bot or the catalogue overrule a 'daily' guess."""
        weekly = {k for k, b in self.cfg.buckets.items() if b.kind == "weekly"} | {DAILY}
        if bucket not in weekly:
            return bucket
        hints = [CATEGORY_BUCKET.get((a.get("category") or "").strip().lower())]
        learned = self.led.lookup_place(a.get("place", ""))
        hints.append(learned["bucket"] if learned else None)
        for text in (a.get("place"), a.get("item")):
            m = catalogue.lookup(text or "")
            hints.append(m.bucket if m else None)
        return next((h for h in hints if h in self.cfg.keep_out_of_daily), bucket)

    def _classify(self, a: dict) -> tuple[str | None, str | None, str]:
        """(bucket, category, source). Order: the model's sure bucket > places the couple taught the bot >
        the merchant catalogue > ask (the model was unsure) > the category's usual bucket. Buckets in
        rules.keep_out_of_daily (Chu Chu) are never left as weekday/weekend."""
        bucket, category, source = self._classify_raw(a)
        kept = self._keep_out_of_daily(bucket, a)
        return (kept, category, "kept-out") if kept != bucket else (bucket, category, source)

    def _classify_raw(self, a: dict) -> tuple[str | None, str | None, str]:
        category = a.get("category") or None
        if a.get("bucket"):
            return a["bucket"], category, "model"
        place = a.get("place", "")
        learned = self.led.lookup_place(place)
        if learned and learned["bucket"]:
            return None, category, "learned"  # the ledger applies what it learned
        m = catalogue.lookup(place)
        if m:
            return m.bucket, category or m.category, "catalogue"
        if a.get("bucket_options"):
            return None, category, "ask"
        if category:
            return CATEGORY_BUCKET.get(category.strip().lower(), DAILY), category, "category"
        return None, category, "ask"

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

    def _not_own_question(self, entry_id: int, ctx: Context) -> None:
        """An answer must come from a later message than the spend: the bot can't answer its own question."""
        e = self.led.entry(entry_id)
        if ctx.msg_id and e["msg_id"] and e["chat_id"] == (ctx.chat_id or None) and \
                e["msg_id"].split(":")[0] == ctx.msg_id and e["needs"]:
            raise LedgerError(f"#{entry_id} is waiting for their answer — post the question and wait; "
                              "don't answer it yourself")

    # ---- handlers ---------------------------------------------------------------------------------
    def log_spend(self, a: dict, ctx: Context) -> dict:
        sender = self._sender(ctx)
        part = int(a.get("part") or 1)
        msg_id = None
        if ctx.msg_id:
            msg_id = ctx.msg_id if part == 1 else f"{ctx.msg_id}:{part}"
        payer = self._person(a.get("paid_by"), ctx)
        bill = self._fixed_bill(a) or self._fixed_from_classify(a)
        if bill:
            return self._pay_bill_instead(bill, a, ctx, payer if payer not in (None, "each") else sender)
        # a plain spend belongs to whoever paid it ("Vanisa paid RM70 sushi" is Vanisa's, whoever types it);
        # only a split / shares / for_person says otherwise. Shared buckets (grocery, Chu Chu, petrol, toll) are
        # split evenly by the ledger, whoever paid.
        owner = payer if payer not in (None, "each") else sender
        total, shares = self._amounts(a, ctx, owner, required=True)
        said = bool(a.get("shares") or a.get("split") or a.get("for_person"))
        bucket, category, _ = self._classify(a)
        e = self.led.log_spend(
            sender=sender, place=a.get("place", ""), total=None if total is None else _rm(total),
            shares={p: _rm(v) for p, v in shares.items()}, paid_by=payer,
            bucket=bucket, category=category, item=a.get("item") or None,
            spent_on=self._day(a.get("date"), ctx), bucket_options=a.get("bucket_options") or None,
            raw_text=textcheck.strip_reply_quote(ctx.text) if ctx.text else None,
            chat_id=ctx.chat_id or None, msg_id=msg_id, shares_given=said)
        return self._spend_result(e)

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
        old = self.led.entry(entry_id)
        total, shares = self._amounts(a, ctx, old["sender"], required=False)
        said = bool(a.get("shares") or a.get("split") or a.get("for_person"))
        if shares is not None and not said:
            # "wrong, should be 30": same people, same proportions, new total
            shares = dict(zip(old["shares"], split_ratio(total, list(old["shares"].values()))))
        e = self.led.edit(entry_id, place=a.get("place"), item=a.get("item"),
                          total=None if total is None else _rm(total),
                          shares=None if shares is None else {p: _rm(v) for p, v in shares.items()},
                          paid_by=self._person(a.get("paid_by"), ctx), bucket=a.get("bucket"),
                          category=a.get("category"),
                          spent_on=self._day(a["date"], ctx) if a.get("date") else None, shares_given=said)
        r = self._spend_result(e)
        r["reply"] = "✏️ " + r["reply"].removeprefix("✅ ")
        return r

    def delete_spend(self, a: dict, ctx: Context) -> dict:
        entry_id = int(a["entry_id"]) if a.get("entry_id") is not None else self._latest(ctx)
        e = self.led.delete(entry_id)
        return {"entry_id": e["id"], "reply": f"🗑️ Deleted #{e['id']} {e['place']} {fmt(e['total_sen'], self.cfg.currency)}"}

    def settle_up(self, a: dict, ctx: Context) -> dict:
        amount = None
        if a.get("amount") not in (None, ""):
            sen = self._sen(a["amount"], "amount")
            self._verify(ctx, {"amount": sen})
            amount = _rm(sen)
        r = self.led.settle(from_person=self._person(a.get("from_person"), ctx),
                            to_person=self._person(a.get("to_person"), ctx), amount=amount,
                            on=self._sent_day(ctx), chat_id=ctx.chat_id or None, msg_id=ctx.msg_id or None)
        if r["duplicate"]:
            return {"reply": "Already recorded."}
        names = self.cfg.people
        return {"reply": f"🤝 {names[r['from']].name} → {names[r['to']].name} {fmt(r['amount'], self.cfg.currency)}\n"
                         f"{replies.balance_line(self.cfg, r['balance'])}"}

    def pay_fixed(self, a: dict, ctx: Context) -> dict:
        person = self._person(a.get("person"), ctx) or self._sender(ctx)
        bills = a.get("bills") or []
        if not bills:
            raise LedgerError("which bill? " + ", ".join(b.label for b in self.cfg.buckets.values()
                                                          if b.kind == "fixed"))
        month = a.get("month") or month_key(self._sent_day(ctx))
        lines = [replies.fixed_reply(self.cfg, self.led.pay_fixed(person, b, month)) for b in bills]
        return {"reply": "\n".join(lines)}

    def set_plan(self, a: dict, ctx: Context) -> dict:
        sen = self._sen(a.get("amount"), "amount")
        self._verify(ctx, {"amount": sen})
        r = self.led.set_plan(a.get("bucket", ""), _rm(sen), self._person(a.get("person"), ctx), a.get("month"))
        names = " & ".join(self.cfg.people[p].name for p in r["people"])
        b = self.cfg.buckets[r["bucket"]]
        per = " per day" if b.kind == "weekly" else ""
        return {"reply": f"📝 {b.label} = {fmt(r['amount'], self.cfg.currency)}{per} for {names} from {r['month']}"}

    def status(self, a: dict, ctx: Context) -> dict:
        st = self.led.status(a.get("month"))
        person = self._person(a.get("person"), ctx)
        bucket = a.get("bucket")
        if bucket:
            b = next((x for x in self.cfg.buckets.values() if bucket.strip().lower() in (x.key, x.label.lower())), None)
            if b is None:
                raise LedgerError(f"unknown bucket {bucket!r}")
            return {"reply": replies.bucket_text(self.cfg, st, b.key, person)}
        return {"reply": replies.status_text(self.cfg, st, person)}

    def list_spends(self, a: dict, ctx: Context) -> dict:
        month = a.get("month") or month_key(self._sent_day(ctx))
        person = self._person(a.get("person"), ctx)
        rows = self.led.list_entries(month, person, a.get("bucket"), a.get("category"),
                                     self._person(a.get("paid_by"), ctx), a.get("query"))
        return {"count": len(rows),
                "reply": replies.spends_text(self.cfg, rows, month, person, a, int(a.get("limit") or 15))}

    def pending(self, a: dict, ctx: Context) -> dict:
        qs = [replies.question(self.cfg, self.led.entry(p["id"])) for p in self.led.pending()]
        return {"count": len(qs), "reply": "\n".join(q["text"] for q in qs) or "Nothing waiting ✓"}

    def lookup_place(self, a: dict, ctx: Context) -> dict:
        return {"place": self.led.lookup_place(a.get("name", ""))}

    def fixed_due(self, a: dict, ctx: Context) -> dict:
        rows = self.led.fixed_due(a.get("month"))
        return {"count": len(rows), "reply": "\n".join(
            f"⏳ @{self.cfg.people[r['person']].name} {self.cfg.buckets[r['bucket']].label} "
            f"{fmt(r['amount_sen'], self.cfg.currency)} is due" for r in rows) or "All fixed bills paid ✓"}

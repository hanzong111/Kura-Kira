"""Write side: every change to the ledger goes through here.

The agent decides *what* a message means (place, amounts, bucket, payer); this module checks it,
stores it, and reports back the numbers for the reply. It never guesses: anything missing is
stored as pending (bucket NULL = Unsorted, paid_by NULL = payer unknown) for the bot to ask about.
"""

from __future__ import annotations

import difflib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Callable, Mapping

from . import report
from .config import DAILY, Config
from .money import parse_amount, split_even
from .periods import month_bounds, month_key, prev_month

EACH = "each"  # paid_by value: everyone paid their own share
# A redelivered message comes back within minutes. Telegram message ids are per bot in a basic group and
# restart when the bot token changes, so an id seen longer ago than this belongs to a different message.
DUP_WINDOW = timedelta(days=1)


class LedgerError(ValueError):
    """Bad input the bot should explain to the user (or ask about)."""


def _crossed(spent: int, cap: int, threshold: float) -> bool:
    """80% means reached 80%; 100% means went over."""
    return spent > cap * threshold if threshold >= 1 else spent >= cap * threshold


def norm_place(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


class Ledger:
    def __init__(self, conn: sqlite3.Connection, cfg: Config, clock: Callable[[], datetime] | None = None):
        self.conn = conn
        self.cfg = cfg
        self._clock = clock

    # ---- time -------------------------------------------------------------------------------------
    def now(self) -> datetime:
        return self._clock() if self._clock else datetime.now(self.cfg.tz)

    def today(self) -> date:
        return self.now().date()

    def _stamp(self) -> str:
        return self.now().isoformat(timespec="seconds")

    def _duplicate(self, table: str, chat_id, msg_id) -> sqlite3.Row | None:
        """The row already recorded for this chat message. Backfill keys are permanent; message ids expire:
        an older row holding the id is retired (msg_id -> 'id~row') so the new message can take it."""
        row = self.conn.execute(f"SELECT id, created_at FROM {table} WHERE chat_id=? AND msg_id=?",
                                (str(chat_id), str(msg_id))).fetchone()
        since = (self.now() - DUP_WINDOW).isoformat(timespec="seconds")
        if row is None or chat_id == "backfill" or row["created_at"] >= since:
            return row
        self.conn.execute(f"UPDATE {table} SET msg_id=? WHERE id=?", (f"{msg_id}~{row['id']}", row["id"]))
        return None

    @contextmanager
    def _tx(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        else:
            self.conn.execute("COMMIT")

    # ---- validation helpers -----------------------------------------------------------------------
    def _person(self, name: str | None) -> str:
        if name is None:
            raise LedgerError("person is required")
        try:
            return self.cfg.person(name).key
        except ValueError as e:
            raise LedgerError(str(e)) from None

    def _date(self, value: str | date | None) -> date:
        if value is None:
            return self.today()
        if isinstance(value, date):
            return value
        v = value.strip().lower()
        if v == "today":
            return self.today()
        if v == "yesterday":
            return self.today() - timedelta(days=1)
        try:
            return date.fromisoformat(v)
        except ValueError:
            raise LedgerError(f"date must be YYYY-MM-DD, 'today' or 'yesterday', got {value!r}") from None

    def _amount(self, value) -> int:
        try:
            sen = parse_amount(value)
        except ValueError as e:
            raise LedgerError(str(e)) from None
        if sen <= 0:
            raise LedgerError(f"amount must be positive, got {value!r}")
        return sen

    def _category(self, value: str | None) -> str | None:
        if not value:
            return None
        for c in self.cfg.categories:
            if c.lower() == value.strip().lower():
                return c
        return value.strip().title()

    def _bucket(self, value: str | None, spent_on: date) -> str | None:
        """'daily' -> weekday/weekend by date; a bucket key/label -> key; None -> Unsorted."""
        if value is None:
            return None
        v = value.strip().lower()
        if v == DAILY:
            return self.cfg.weekly_bucket_for(spent_on.weekday()).key
        for b in self.cfg.buckets.values():
            if v in (b.key, b.label.lower()):
                if b.kind == "fixed":
                    raise LedgerError(f"{b.label} is a fixed bill — use pay_fixed, not a spend")
                return b.key
        raise LedgerError(f"unknown bucket {value!r} (use 'daily' or one of: "
                          f"{', '.join(k for k, b in self.cfg.buckets.items() if b.kind != 'fixed')})")

    def _shares(self, sender: str, total, shares: Mapping[str, object] | None) -> tuple[int, dict[str, int]]:
        if shares:
            parsed = {self._person(p): self._amount(a) for p, a in shares.items()}
            share_sum = sum(parsed.values())
            if total is None:
                return share_sum, parsed
            total_sen = self._amount(total)
            if share_sum != total_sen:
                raise LedgerError(f"shares add up to {share_sum / 100:.2f} but the total is "
                                  f"{total_sen / 100:.2f} — ask which is right")
            return total_sen, parsed
        if total is None:
            raise LedgerError("amount is missing — ask how much")
        total_sen = self._amount(total)
        return total_sen, {sender: total_sen}

    def _borne(self, total_sen: int, share_map: dict[str, int], bucket_key: str | None, given: bool,
               payer: str | None, sender: str) -> dict[str, int]:
        """Whose cost it is, when the message didn't say: a shared bucket (grocery, Chu Chu, petrol, toll)
        is split evenly between everyone whoever paid; anything else belongs to whoever paid."""
        if given:
            return share_map
        if bucket_key and self.cfg.buckets[bucket_key].shared:
            people = list(self.cfg.people)
            return dict(zip(people, split_even(total_sen, len(people))))
        if len(share_map) == 1:
            return {next(iter(share_map)): total_sen}
        # was split by the shared rule, now in a bucket that isn't shared
        return {payer if payer in self.cfg.people else sender: total_sen}

    def _payer(self, paid_by: str | None, sender: str, shares: dict[str, int]) -> str | None:
        if paid_by is None:
            # only the sender involved -> the sender paid; anyone else involved -> ask
            return sender if set(shares) == {sender} else None
        if paid_by.strip().lower() in (EACH, "each paid own", "own"):
            return EACH
        return self._person(paid_by)

    # ---- months & plans ---------------------------------------------------------------------------
    def ensure_month(self, month: str | None = None) -> str:
        """Create the month's plan (copied from last month, else config) and fixed-bill rows. A bucket added
        to the config later (e.g. an installment) gets its plan row in months that already exist."""
        month = month or month_key(self.today())
        month_bounds(month)  # validates format
        buckets = self.cfg.buckets_in(month)
        with self._tx():
            prev = self.conn.execute("SELECT person, bucket, amount_sen FROM plans WHERE month=?",
                                     (prev_month(month),)).fetchall()
            rows = {(r["person"], r["bucket"]): r["amount_sen"] for r in prev}
            for p in self.cfg.people:
                for k, b in buckets.items():
                    if not b.applies_to(p):
                        continue
                    amt = rows.get((p, k), b.amount_sen)
                    self.conn.execute("INSERT OR IGNORE INTO plans VALUES (?,?,?,?)", (month, p, k, amt))
            for p in self.cfg.people:
                for k, b in buckets.items():
                    if b.kind != "fixed" or not b.applies_to(p):
                        continue
                    amt = report.plan_amount(self.conn, month, p, k)
                    auto = p in b.auto_paid
                    self.conn.execute(
                        "INSERT OR IGNORE INTO fixed_payments(month, person, bucket, amount_sen, paid_at, auto) "
                        "VALUES (?,?,?,?,?,?)",
                        (month, p, k, amt, self._stamp() if auto else None, int(auto)))
        return month

    def set_plan(self, bucket: str, amount, person: str | None = None, month: str | None = None) -> dict:
        """Set a bucket's monthly amount for one person (or everyone when person is None)."""
        month = self.ensure_month(month)
        b = next((x for x in self.cfg.buckets.values() if bucket.strip().lower() in (x.key, x.label.lower())), None)
        if b is None:
            raise LedgerError(f"unknown bucket {bucket!r}")
        try:
            sen = parse_amount(amount)
        except ValueError as e:
            raise LedgerError(str(e)) from None
        if sen < 0:
            raise LedgerError("plan amount can't be negative")
        people = [self._person(person)] if person else [p for p in self.cfg.people if b.applies_to(p)]
        if not all(b.applies_to(p) for p in people):
            raise LedgerError(f"{b.label} is only {', '.join(self.cfg.people[x].name for x in b.people)}'s bill")
        with self._tx():
            for p in people:
                self.conn.execute("UPDATE plans SET amount_sen=? WHERE month=? AND person=? AND bucket=?",
                                  (sen, month, p, b.key))
                if b.kind == "fixed":
                    self.conn.execute("UPDATE fixed_payments SET amount_sen=? WHERE month=? AND person=? AND bucket=?",
                                      (sen, month, p, b.key))
        return {"month": month, "bucket": b.key, "amount": sen, "people": people}

    # ---- places -----------------------------------------------------------------------------------
    def lookup_place(self, name: str) -> dict | None:
        """Best learned match for a place name (exact after normalising, else close spelling)."""
        key = norm_place(name)
        if not key:
            return None
        row = self.conn.execute("SELECT * FROM places WHERE key=?", (key,)).fetchone()
        if row is None:
            keys = [r[0] for r in self.conn.execute("SELECT key FROM places")]
            close = difflib.get_close_matches(key, keys, n=1, cutoff=0.85)
            if close:
                row = self.conn.execute("SELECT * FROM places WHERE key=?", (close[0],)).fetchone()
        return dict(row) if row else None

    def learn_place(self, name: str, bucket: str | None = None, category: str | None = None,
                    display: str | None = None) -> None:
        key = norm_place(name)
        if not key or (bucket is None and category is None):
            return
        if bucket is not None and bucket != DAILY:
            bucket = self._bucket(bucket, self.today())
            if self.cfg.buckets[bucket].kind == "weekly":
                bucket = DAILY  # remember "everyday spending"; weekday/weekend is picked by date each time
        self.conn.execute(
            """INSERT INTO places(key, display, bucket, category, uses) VALUES (?,?,?,?,1)
               ON CONFLICT(key) DO UPDATE SET
                 bucket = COALESCE(excluded.bucket, places.bucket),
                 category = COALESCE(excluded.category, places.category),
                 display = excluded.display,
                 uses = places.uses + 1""",
            (key, display or name.strip(), bucket, self._category(category)))

    # ---- spends -----------------------------------------------------------------------------------
    def log_spend(self, *, sender: str, place: str, total=None, shares: Mapping[str, object] | None = None,
                  paid_by: str | None = None, bucket: str | None = None, category: str | None = None,
                  item: str | None = None, spent_on: str | date | None = None, bucket_options: list[str] | None = None,
                  raw_text: str | None = None, chat_id: str | None = None, msg_id: str | None = None,
                  shares_given: bool | None = None) -> dict:
        """Record one spend message. Returns the entry plus what the reply should say.

        bucket: 'daily' (weekday/weekend by date), a bucket key, or None (unknown -> learned place,
        else Unsorted and the bot asks). paid_by: person, 'each', or None (sender if only the sender
        is involved, else unknown and the bot asks). shares_given: the message said whose it is (a split,
        stated shares, "for Vanisa"); otherwise shared buckets are split evenly. Defaults to bool(shares).
        """
        sender = self._person(sender)
        place = (place or "").strip()
        if not place:
            raise LedgerError("place/item is required")
        if chat_id is not None and msg_id is not None:
            dup = self._duplicate("entries", chat_id, msg_id)
            if dup:
                return {**self.entry(dup["id"]), "duplicate": True}

        day = self._date(spent_on)
        stated_payer = None if paid_by is None or paid_by.strip().lower() in (EACH, "each paid own", "own") \
            else self._person(paid_by)
        # no shares given: it's the payer's own spend (falls back to the sender)
        total_sen, share_map = self._shares(stated_payer or sender, total, shares)
        payer = self._payer(paid_by, sender, share_map)

        learned = self.lookup_place(place)
        given_bucket = bucket
        if bucket is None and learned and learned["bucket"]:
            bucket = learned["bucket"]
        if category is None and learned:
            category = learned["category"]
        bucket_key = self._bucket(bucket, day)
        category = self._category(category)
        given = bool(shares) if shares_given is None else bool(shares_given)
        share_map = self._borne(total_sen, share_map, bucket_key, given, payer, sender)

        month = self.ensure_month(month_key(day))
        before = self._snapshot(month, share_map, bucket_key, day)
        with self._tx():
            cur = self.conn.execute(
                """INSERT INTO entries(created_at, spent_on, place, item, category, bucket, bucket_options,
                                       total_sen, shares_given, paid_by, sender, raw_text, chat_id, msg_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (self._stamp(), day.isoformat(), place, item, category, bucket_key,
                 json.dumps(bucket_options) if bucket_options else None, total_sen, int(given), payer, sender,
                 raw_text,
                 None if chat_id is None else str(chat_id), None if msg_id is None else str(msg_id)))
            entry_id = cur.lastrowid
            for p, amt in share_map.items():
                self.conn.execute("INSERT INTO shares VALUES (?,?,?)", (entry_id, p, amt))
            if given_bucket is not None or category is not None:
                self.learn_place(place, given_bucket if given_bucket is not None else
                                 (learned["bucket"] if learned else None), category)
        return self._result(entry_id, month, before, day)

    def entry(self, entry_id: int) -> dict:
        row = self.conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
        if row is None:
            raise LedgerError(f"no entry #{entry_id}")
        e = dict(row)
        e["shares"] = {r["person"]: r["amount_sen"]
                       for r in self.conn.execute("SELECT person, amount_sen FROM shares WHERE entry_id=? "
                                                  "ORDER BY person", (entry_id,))}
        e["bucket_options"] = json.loads(e["bucket_options"]) if e["bucket_options"] else None
        e["needs"] = [n for n, missing in (("bucket", e["bucket"] is None), ("payer", e["paid_by"] is None))
                      if missing]
        return e

    def _snapshot(self, month: str, share_map: dict[str, int], bucket_key: str | None, day: date) -> dict:
        if bucket_key is None:
            return {}
        return {p: report.bucket_status(self.conn, self.cfg, month, p, bucket_key, self._view_day(month, day))
                for p in share_map}

    def _view_day(self, month: str, day: date) -> date:
        """Status is shown as of today, or as of the spend date when logging into another month."""
        today = self.today()
        first, last = month_bounds(month)
        return today if first <= today <= last else day

    def _result(self, entry_id: int, month: str, before: dict, day: date) -> dict:
        e = self.entry(entry_id)
        after = self._snapshot(month, e["shares"], e["bucket"], day)
        e["status"] = after
        e["alerts"] = self._alerts(before, after)
        b = self.cfg.buckets.get(e["bucket"]) if e["bucket"] else None
        e["ask_extra"] = bool(b and b.kind == "weekly"
                              and any(a > self.cfg.ask_extra_over_sen for a in e["shares"].values()))
        e["duplicate"] = False
        return e

    def _alerts(self, before: dict, after: dict) -> list[dict]:
        out = []
        for p, a in after.items():
            b = before.get(p)
            if b is None:
                continue
            scope = "week" if "week" in a else "month"
            cur, prev = (a["week"], b["week"]) if scope == "week" else (a, b)
            cap = cur["allowance"] if scope == "week" else cur["cap"]
            for t in self.cfg.alert_at:
                was = _crossed(prev["spent"], cap, t)
                now = _crossed(cur["spent"], cap, t)
                if now and not was:
                    out.append({"person": p, "bucket": a["bucket"], "scope": scope, "threshold": t,
                                "spent": cur["spent"], "cap": cap, "left": cap - cur["spent"]})
        # keep only the highest threshold crossed per person/bucket
        best: dict[tuple, dict] = {}
        for al in out:
            k = (al["person"], al["bucket"])
            if k not in best or al["threshold"] > best[k]["threshold"]:
                best[k] = al
        return list(best.values())

    def resolve(self, entry_id: int, *, bucket: str | None = None, category: str | None = None,
                paid_by: str | None = None, learn: bool = True) -> dict:
        """Apply the answer to a clarifying question (bucket and/or payer)."""
        e = self.entry(entry_id)
        if e["deleted_at"]:
            raise LedgerError(f"entry #{entry_id} was deleted")
        day = date.fromisoformat(e["spent_on"])
        month = month_key(day)
        new_bucket = self._bucket(bucket, day) if bucket is not None else e["bucket"]
        new_payer = self._payer(paid_by, e["sender"], e["shares"]) if paid_by is not None else e["paid_by"]
        new_cat = self._category(category) if category is not None else e["category"]
        share_map = self._borne(e["total_sen"], e["shares"], new_bucket, bool(e["shares_given"]), new_payer,
                                e["sender"])
        before = self._snapshot(month, share_map, new_bucket, day) if new_bucket != e["bucket"] else {}
        with self._tx():
            self.conn.execute("UPDATE entries SET bucket=?, paid_by=?, category=? WHERE id=?",
                              (new_bucket, new_payer, new_cat, entry_id))
            if share_map != e["shares"]:
                self._write_shares(entry_id, share_map)
            if learn and (bucket is not None or category is not None):
                self.learn_place(e["place"], bucket, category)
        return self._result(entry_id, month, before, day)

    def edit(self, entry_id: int, *, place: str | None = None, item: str | None = None, total=None,
             shares: Mapping[str, object] | None = None, paid_by: str | None = None, bucket: str | None = None,
             category: str | None = None, spent_on: str | date | None = None,
             shares_given: bool | None = None) -> dict:
        """shares_given: the new shares were said in the message (None: True when shares are passed)."""
        e = self.entry(entry_id)
        if e["deleted_at"]:
            raise LedgerError(f"entry #{entry_id} was deleted")
        day = self._date(spent_on) if spent_on is not None else date.fromisoformat(e["spent_on"])
        # once said in a message, whose it is stays said; otherwise the rule decides again below
        given = bool(shares is not None if shares_given is None else shares_given) or bool(e["shares_given"])
        if shares is not None or total is not None:
            if shares is None and len(e["shares"]) > 1 and given:
                raise LedgerError(f"#{entry_id} is split between people — give the new shares, not just a total")
            if shares is None:
                shares = {next(iter(e["shares"])): total}
                total = None
            total_sen, share_map = self._shares(e["sender"], total, shares)
        else:
            total_sen, share_map = e["total_sen"], e["shares"]
        payer = e["paid_by"]
        if paid_by is not None:
            payer = self._payer(paid_by, e["sender"], share_map)
        if bucket is not None:
            bucket_key = self._bucket(bucket, day)
        elif e["bucket"] and spent_on is not None and self.cfg.buckets[e["bucket"]].kind == "weekly":
            bucket_key = self._bucket(DAILY, day)  # date moved: re-pick weekday/weekend
        else:
            bucket_key = e["bucket"]
        share_map = self._borne(total_sen, share_map, bucket_key, given, payer, e["sender"])
        self.ensure_month(month_key(day))
        with self._tx():
            self.conn.execute(
                """UPDATE entries SET place=?, item=?, total_sen=?, shares_given=?, paid_by=?, bucket=?, category=?,
                   spent_on=? WHERE id=?""",
                ((place or e["place"]).strip(), item if item is not None else e["item"], total_sen, int(given),
                 payer, bucket_key, self._category(category) if category is not None else e["category"],
                 day.isoformat(), entry_id))
            self._write_shares(entry_id, share_map)
            if bucket is not None or category is not None:
                self.learn_place(place or e["place"], bucket, category)
        return self._result(entry_id, month_key(day), {}, day)

    def _write_shares(self, entry_id: int, share_map: dict[str, int]) -> None:
        self.conn.execute("DELETE FROM shares WHERE entry_id=?", (entry_id,))
        for p, amt in share_map.items():
            self.conn.execute("INSERT INTO shares VALUES (?,?,?)", (entry_id, p, amt))

    def reshare(self) -> list[dict]:
        """Re-apply the whose-cost rule to every entry whose shares weren't said in the message (after a
        bucket becomes shared, or stops being shared). Returns what changed."""
        changed = []
        for row in self.conn.execute("SELECT id FROM entries WHERE deleted_at IS NULL AND shares_given = 0 "
                                     "ORDER BY id").fetchall():
            e = self.entry(row["id"])
            new = self._borne(e["total_sen"], e["shares"], e["bucket"], False, e["paid_by"], e["sender"])
            if new != e["shares"]:
                with self._tx():
                    self._write_shares(e["id"], new)
                changed.append({"id": e["id"], "place": e["place"], "before": e["shares"], "after": new})
        return changed

    def delete(self, entry_id: int) -> dict:
        e = self.entry(entry_id)
        if e["deleted_at"]:
            raise LedgerError(f"entry #{entry_id} is already deleted")
        with self._tx():
            self.conn.execute("UPDATE entries SET deleted_at=? WHERE id=?", (self._stamp(), entry_id))
        return self.entry(entry_id)

    def restore(self, entry_id: int) -> dict:
        with self._tx():
            self.conn.execute("UPDATE entries SET deleted_at=NULL WHERE id=?", (entry_id,))
        return self.entry(entry_id)

    def undo(self, sender: str) -> dict:
        """Delete the sender's most recent entry."""
        sender = self._person(sender)
        row = self.conn.execute("SELECT id FROM entries WHERE sender=? AND deleted_at IS NULL "
                                "ORDER BY id DESC LIMIT 1", (sender,)).fetchone()
        if row is None:
            raise LedgerError("nothing to undo")
        return self.delete(row["id"])

    def set_question(self, entry_id: int, question_msg_id: str) -> None:
        self.entry(entry_id)
        self.conn.execute("UPDATE entries SET question_msg_id=? WHERE id=?", (str(question_msg_id), entry_id))

    def find_by_message(self, msg_id: str, chat_id: str | None = None) -> dict | None:
        """Entry for a chat message: either the original spend or the bot's question about it."""
        # several spends in one message are logged as msg_id, msg_id:2, msg_id:3 ...
        params: list = [str(msg_id), f"{msg_id}:%", str(msg_id)]
        chat_sql = ""
        if chat_id is not None:
            chat_sql = " AND chat_id=?"
            params.append(str(chat_id))
        row = self.conn.execute(f"SELECT id FROM entries WHERE (msg_id=? OR msg_id LIKE ? OR question_msg_id=?)"
                                f"{chat_sql} ORDER BY id DESC LIMIT 1", params).fetchone()
        return self.entry(row["id"]) if row else None

    # ---- settle-ups & fixed bills -----------------------------------------------------------------
    def settle(self, *, from_person: str, to_person: str, amount=None, on: str | date | None = None,
               raw_text: str | None = None, chat_id: str | None = None, msg_id: str | None = None) -> dict:
        """Record money paid back. amount None = settle the whole current balance."""
        a, b = self._person(from_person), self._person(to_person)
        if a == b:
            raise LedgerError("settle-up needs two different people")
        if chat_id is not None and msg_id is not None:
            dup = self._duplicate("settlements", chat_id, msg_id)
            if dup:
                return {"id": dup["id"], "duplicate": True, "balance": report.balance(self.conn, self.cfg)}
        if amount is None:
            owes = report.balance(self.conn, self.cfg)["owes"]
            if not owes or owes["from"] != a or owes["to"] != b:
                raise LedgerError(f"{self.cfg.people[a].name} doesn't owe {self.cfg.people[b].name} anything")
            sen = owes["amount"]
        else:
            sen = self._amount(amount)
        with self._tx():
            cur = self.conn.execute(
                "INSERT INTO settlements(created_at, settled_on, from_person, to_person, amount_sen, raw_text, "
                "chat_id, msg_id) VALUES (?,?,?,?,?,?,?,?)",
                (self._stamp(), self._date(on).isoformat(), a, b, sen, raw_text,
                 None if chat_id is None else str(chat_id), None if msg_id is None else str(msg_id)))
        return {"id": cur.lastrowid, "amount": sen, "from": a, "to": b, "duplicate": False,
                "balance": report.balance(self.conn, self.cfg)}

    def pay_fixed(self, person: str, bucket: str, month: str | None = None) -> dict:
        """Mark a fixed bill (house/car) paid for the month. Repeats are harmless."""
        p = self._person(person)
        b = next((x for x in self.cfg.buckets.values() if bucket.strip().lower() in (x.key, x.label.lower())), None)
        if b is None or b.kind != "fixed":
            raise LedgerError(f"{bucket!r} is not a fixed bill "
                              f"({', '.join(k for k, x in self.cfg.buckets.items() if x.kind == 'fixed')})")
        month = month or month_key(self.today())
        if not b.applies_to(p):
            raise LedgerError(f"{b.label} is only {', '.join(self.cfg.people[x].name for x in b.people)}'s bill")
        if not b.active(month):
            raise LedgerError(f"{b.label} only runs in {', '.join(b.months)}")
        month = self.ensure_month(month)
        row = self.conn.execute("SELECT * FROM fixed_payments WHERE month=? AND person=? AND bucket=?",
                                (month, p, b.key)).fetchone()
        if row["paid_at"]:
            return {"month": month, "person": p, "bucket": b.key, "amount": row["amount_sen"],
                    "already_paid": True, "paid_at": row["paid_at"]}
        stamp = self._stamp()
        with self._tx():
            self.conn.execute("UPDATE fixed_payments SET paid_at=? WHERE month=? AND person=? AND bucket=?",
                              (stamp, month, p, b.key))
        out = {"month": month, "person": p, "bucket": b.key, "amount": row["amount_sen"],
               "already_paid": False, "paid_at": stamp}
        if b.months:
            out["installment"] = report.installment(self.conn, b, p)
        return out

    def fixed_due(self, month: str | None = None) -> list[dict]:
        month = self.ensure_month(month)
        bills = self.cfg.buckets_in(month)
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM fixed_payments WHERE month=? AND paid_at IS NULL ORDER BY person, bucket", (month,))
            if r["bucket"] in bills and bills[r["bucket"]].applies_to(r["person"])]

    # ---- reads ------------------------------------------------------------------------------------
    def status(self, month: str | None = None) -> dict:
        month = self.ensure_month(month)
        return report.status(self.conn, self.cfg, month, self.today())

    def pending(self) -> list[dict]:
        return report.pending(self.conn)

    def balance(self) -> dict:
        return report.balance(self.conn, self.cfg)

    def list_entries(self, month: str | None = None, person: str | None = None, bucket: str | None = None,
                     category: str | None = None, paid_by: str | None = None, query: str | None = None,
                     include_deleted: bool = False) -> list[dict]:
        month = month or month_key(self.today())
        first, last = month_bounds(month)
        sql = ["SELECT DISTINCT e.id FROM entries e JOIN shares s ON s.entry_id = e.id "
               "WHERE e.spent_on BETWEEN ? AND ?"]
        params: list = [first.isoformat(), last.isoformat()]
        if not include_deleted:
            sql.append("AND e.deleted_at IS NULL")
        if person:
            sql.append("AND s.person = ?")
            params.append(self._person(person))
        if bucket:
            if bucket.lower() in ("unsorted", "none"):
                sql.append("AND e.bucket IS NULL")
            else:
                sql.append("AND e.bucket = ?")
                params.append(self._bucket(bucket, first))
        if category:
            sql.append("AND lower(e.category) = lower(?)")
            params.append(category)
        if paid_by:
            sql.append("AND e.paid_by = ?")
            params.append(EACH if paid_by.lower() == EACH else self._person(paid_by))
        if query:
            sql.append("AND (e.place LIKE ? OR e.item LIKE ? OR e.raw_text LIKE ?)")
            params += [f"%{query}%"] * 3
        sql.append("ORDER BY e.spent_on DESC, e.id DESC")
        return [self.entry(r["id"]) for r in self.conn.execute(" ".join(sql), params)]

"""Load the plan (people, buckets, rules) from config.toml."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from .money import parse_amount

ROOT = Path(__file__).resolve().parent.parent
KINDS = ("weekly", "monthly", "fixed")
DAILY = "daily"  # pseudo-bucket: resolved to the weekly bucket whose `days` include the spend date


@dataclass(frozen=True)
class Person:
    key: str
    name: str
    telegram_id: int = 0


@dataclass(frozen=True)
class Bucket:
    key: str
    label: str
    kind: str
    amount_sen: int
    days: tuple[int, ...] = ()
    auto_paid: tuple[str, ...] = ()


@dataclass(frozen=True)
class Config:
    timezone: str
    currency: str
    people: dict[str, Person]
    buckets: dict[str, Bucket]
    categories: tuple[str, ...]
    alert_at: tuple[float, ...] = (0.8, 1.0)
    ask_extra_over_sen: int = 10000
    tracking_start: date | None = None  # when tracking began (weekly budgets only)
    telegram_chat_id: str = ""           # the group scheduled messages are posted to
    before_start: str = "ignore"         # pre-start days: "ignore" (prorate from start) or "maxed" (on budget)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def person_by_telegram(self, telegram_id: int) -> Person | None:
        return next((p for p in self.people.values() if p.telegram_id and p.telegram_id == telegram_id), None)

    def person(self, name: str) -> Person:
        """Find a person by key or display name (case-insensitive)."""
        n = name.strip().lower()
        for p in self.people.values():
            if n in (p.key, p.name.lower()):
                return p
        raise ValueError(f"unknown person: {name!r} (known: {', '.join(self.people)})")

    def weekly_bucket_for(self, weekday: int) -> Bucket:
        for b in self.buckets.values():
            if b.kind == "weekly" and weekday in b.days:
                return b
        raise ValueError(f"no weekly bucket covers weekday {weekday}")


def parse(data: dict) -> Config:
    people = {k: Person(k, v.get("name", k.title()), int(v.get("telegram_id", 0)))
              for k, v in data["people"].items()}
    buckets = {}
    for k, v in data["buckets"].items():
        kind = v["kind"]
        if kind not in KINDS:
            raise ValueError(f"bucket {k}: kind must be one of {KINDS}")
        auto = tuple(v.get("auto_paid", ()))
        for p in auto:
            if p not in people:
                raise ValueError(f"bucket {k}: auto_paid names unknown person {p!r}")
        buckets[k] = Bucket(k, v.get("label", k.title()), kind, parse_amount(v["amount"]),
                            tuple(v.get("days", ())), auto)
    covered = sorted(d for b in buckets.values() if b.kind == "weekly" for d in b.days)
    if covered and covered != sorted(set(covered)):
        raise ValueError("weekly buckets overlap on some weekday")
    rules = data.get("rules", {})
    return Config(
        timezone=data.get("timezone", "Asia/Kuala_Lumpur"),
        currency=data.get("currency", "RM"),
        people=people,
        buckets=buckets,
        categories=tuple(rules.get("categories", ())),
        alert_at=tuple(rules.get("alert_at", (0.8, 1.0))),
        ask_extra_over_sen=parse_amount(rules.get("ask_extra_over", 100)),
        tracking_start=_date(rules.get("tracking_start")),
        telegram_chat_id=str(data.get("telegram", {}).get("chat_id", "") or ""),
        before_start=_before_start(rules.get("before_start", "ignore")),
    )


def _before_start(v: str) -> str:
    if v not in ("ignore", "maxed"):
        raise ValueError(f"rules.before_start must be 'ignore' or 'maxed', got {v!r}")
    return v


def _date(v) -> date | None:
    if v in (None, ""):
        return None
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def load(path: str | os.PathLike | None = None) -> Config:
    """config.toml if present, else the committed example."""
    if path is None:
        path = os.environ.get("DUIT_CONFIG")
    if path is None:
        path = ROOT / "config.toml"
        if not path.exists():
            path = ROOT / "config.example.toml"
    with open(path, "rb") as f:
        return parse(tomllib.load(f))

"""Deterministic handling of answers to the bot's questions.

When someone replies to a bot question that carries "#N", and their words match exactly one of the
offered options, code applies the answer: no model involved. Anything unclear is left to the model.
"""

from __future__ import annotations

import re

from .config import DAILY, Config

ENTRY_REF = re.compile(r"#(\d+)\b")

# extra words that mean a bucket (on top of its key and label)
BUCKET_WORDS = {
    DAILY: ("everyday", "every day", "daily", "normal", "weekday", "weekend"),
    "chuchu": ("chu chu", "chuchu", "toiletries", "toiletry", "cat", "pet", "kitty"),
    "grocery": ("grocery", "groceries", "supermarket"),
    "petrol": ("petrol", "fuel", "minyak"),
    "toll": ("toll", "tol", "smarttag", "tng"),
    "parents": ("parents", "parent", "mum", "mom", "dad", "family"),
    "extra": ("extra",),
}
CATEGORY_WORDS = {"toiletries": "Toiletries", "toiletry": "Toiletries", "cat": "Pet", "pet": "Pet",
                  "groceries": "Groceries", "grocery": "Groceries", "petrol": "Transport", "toll": "Transport"}


def referenced_entry(quoted: str | None) -> int | None:
    """The #N in the bot message being replied to."""
    if not quoted:
        return None
    m = ENTRY_REF.search(quoted)
    return int(m.group(1)) if m else None


def _has(text: str, word: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text) is not None


def match_bucket(cfg: Config, text: str, options: list[str]) -> str | None:
    """The single offered bucket the text names, else None."""
    t = text.lower()
    hits = set()
    for key in options:
        words = set(BUCKET_WORDS.get(key, ()))
        if key in cfg.buckets:
            words |= {key, cfg.buckets[key].label.lower()}
            words |= {w.strip() for w in cfg.buckets[key].label.lower().split("/")}
        if any(_has(t, w) for w in words if w):
            hits.add(key)
    return hits.pop() if len(hits) == 1 else None


def match_category(cfg: Config, text: str) -> str | None:
    t = text.lower()
    found = {c for c in cfg.categories if _has(t, c.lower())}
    found |= {v for k, v in CATEGORY_WORDS.items() if _has(t, k)}
    return found.pop() if len(found) == 1 else None


def match_payer(cfg: Config, text: str, sender: str) -> str | None:
    t = text.lower()
    if _has(t, "each") or "own" in t.split():
        return "each"
    hits = {p for p, person in cfg.people.items() if _has(t, person.key) or _has(t, person.name.lower())}
    if re.search(r"\b(i|me)\b\s*(paid|pay)?|\bmine\b", t):
        hits.add(sender)
    return hits.pop() if len(hits) == 1 else None


def interpret(cfg: Config, entry: dict, text: str, sender: str) -> dict | None:
    """Arguments for Ledger.resolve if the reply clearly answers what the entry needs, else None."""
    if not entry or entry.get("deleted_at") or not entry["needs"]:
        return None
    if "payer" in entry["needs"]:
        payer = match_payer(cfg, text, sender)
        return {"paid_by": payer} if payer else None
    if "bucket" in entry["needs"]:
        options = entry.get("bucket_options") or [DAILY, "extra"]
        bucket = match_bucket(cfg, text, options)
        if bucket is None:
            return None
        out = {"bucket": bucket}
        category = match_category(cfg, text)
        if category:
            out["category"] = category
        return out
    return None

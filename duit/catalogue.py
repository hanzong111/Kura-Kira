"""Merchant catalogue: known Malaysian shops, restaurants and venues -> bucket + category.

`catalogue/merchants.csv` (name|aliases|bucket|category|group) is compiled from web research by
`scripts/build_catalogue.py`. It's consulted
when the model doesn't give a bucket (or isn't sure), after the places the couple has taught the bot.
Matching is deterministic: the whole place name, or a catalogue name appearing as whole words in it
("jaya grocer bangsar" -> Jaya Grocer). Short aliases (3 letters or fewer, e.g. "kk", "tpc") and ones
marked "=alias" (ordinary words like "dome", "five") only match the whole place name.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config import ROOT

PATH = ROOT / "catalogue" / "merchants.csv"
BUCKETS = {"daily", "grocery", "chuchu", "petrol", "toll", "parents", "extra"}


@dataclass(frozen=True)
class Merchant:
    name: str
    bucket: str
    category: str
    matched: str  # the name/alias that matched


def _words(s: str) -> str:
    """Lowercase, punctuation to spaces, single-spaced: "Nando's" -> "nando s", "7-Eleven" -> "7 eleven"."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s.lower()).split())


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


@lru_cache(maxsize=4)
def load(path: Path = PATH) -> tuple[dict[str, Merchant], list[tuple[str, Merchant]]]:
    """(exact index by squashed name, phrase list longest-first for whole-word search)."""
    exact: dict[str, Merchant] = {}
    phrases: list[tuple[str, Merchant]] = []
    if not path.exists():
        return exact, phrases
    with open(path, newline="", encoding="utf-8") as f:
        lines = (ln for ln in f if not ln.startswith("#"))
        for row in csv.DictReader(lines, delimiter="|"):
            raw_name, bucket, category = row["name"].strip(), row["bucket"].strip(), row["category"].strip()
            name = raw_name.lstrip("=")
            if not name or bucket not in BUCKETS:
                continue
            for alias in [raw_name] + [a for a in (row.get("aliases") or "").split(";")]:
                alias = alias.strip()
                whole_only = alias.startswith("=")
                alias = alias.lstrip("=")
                if not alias:
                    continue
                m = Merchant(name, bucket, category, alias)
                exact.setdefault(_squash(alias), m)
                if not whole_only and len(_squash(alias)) > 3:
                    phrases.append((_words(alias), m))
    phrases.sort(key=lambda p: -len(p[0]))
    return exact, phrases


def lookup(place: str, path: Path = PATH) -> Merchant | None:
    exact, phrases = load(path)
    key = _squash(place)
    if not key:
        return None
    if key in exact:
        return exact[key]
    text = f" {_words(place)} "
    for phrase, m in phrases:
        if f" {phrase} " in text:
            return m
    return None

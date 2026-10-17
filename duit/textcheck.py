"""Check the model's numbers against the message the user actually sent.

The model reads messages; it doesn't get to invent amounts. Every amount it passes must appear in the
original text (as RM13.20, 13.2, 13.20, rm 13 ...). Numbers that are clearly not money — headcounts
("2 pax"), ratios ("2:1"), times ("7pm", "10:30"), entry refs ("#142"), dates ("18/10") — are ignored.
"""

from __future__ import annotations

import re

from .money import parse_amount

# a number, optionally with RM before/after; captured with its surroundings so we can skip non-money
_NUM = re.compile(r"(?<![\w#.:/])(?:rm|myr)?\s*(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?|\.\d{1,2})(?![\d.,:/]\d)(?!-[a-z])", re.I)
_NOT_MONEY_AFTER = re.compile(
    r"^\s*(?:pax|people|ppl|persons?|pcs|pieces?|x\b|times|min|mins|minutes?|hrs?|hours?|am\b|pm\b|km|kg|%|"
    r"days?|weeks?|months?|years?|yrs?|nights?|st\b|nd\b|rd\b|th\b)", re.I)
_RATIO = re.compile(r"\d+\s*:\s*\d+")
_TIME = re.compile(r"\b\d{1,2}[:.]\d{2}\s*(?:am|pm)\b|\b\d{1,2}:\d{2}\b", re.I)
_DATE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")


def strip_reply_quote(text: str) -> str:
    """Drop the gateway's '[Replying to X: "..."]' prefix: numbers in the quoted bot message don't count."""
    if text.startswith("[Replying to"):
        end = text.find("]\n")
        if end != -1:
            return text[end + 1:].lstrip()
    return text


def money_numbers(text: str | None) -> list[int]:
    """Amounts (in sen) mentioned in a message, in order. Empty list for no text."""
    if not text:
        return []
    text = strip_reply_quote(text)
    masked = _TIME.sub(" ", text)
    masked = _DATE.sub(" ", masked)
    masked = _RATIO.sub(" ", masked)
    out = []
    for m in _NUM.finditer(masked):
        if _NOT_MONEY_AFTER.match(masked[m.end():]):
            continue
        if masked[max(0, m.start() - 1):m.start()].lower() == "x":   # "x2"
            continue
        try:
            out.append(parse_amount(m.group(1)))
        except ValueError:
            continue
    return out


def check_amounts(text: str | None, amounts: dict[str, int]) -> str | None:
    """None if every amount appears in the message; else a question for the bot to ask.

    `amounts` maps a label ("total", "Hanz's share") to sen. Without the original text there's
    nothing to check against, so it passes (CLI / tests without a message).
    """
    if text is None:
        return None
    found = set(money_numbers(text))
    for label, sen in amounts.items():
        if sen not in found:
            return (f"I can't find {sen / 100:.2f} ({label}) in the message — ask them to confirm the amount "
                    "instead of guessing")
    return None


def unused_numbers(text: str | None, used: list[int]) -> list[int]:
    """Money-looking numbers in the message that weren't used (e.g. a total next to shares)."""
    if text is None:
        return []
    remaining = list(used)
    out = []
    for n in money_numbers(text):
        if n in remaining:
            remaining.remove(n)
        else:
            out.append(n)
    return out

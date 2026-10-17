"""Money is stored as integer sen (1 RM = 100 sen) so totals never drift."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_AMOUNT = re.compile(r"^\s*(?:rm|myr)?\s*(-?\d+(?:,\d{3})*(?:\.\d{1,2})?|-?\.\d{1,2})\s*(?:rm|myr)?\s*$", re.I)


def parse_amount(value: str | int | float | Decimal) -> int:
    """'RM13.20', '13.2', 'rm 56', 56.5 -> sen. Raises ValueError on anything else."""
    if isinstance(value, bool):
        raise ValueError(f"not an amount: {value!r}")
    if isinstance(value, int):
        return value * 100
    if isinstance(value, (float, Decimal)):
        d = Decimal(str(value))
    else:
        m = _AMOUNT.match(str(value))
        if not m:
            raise ValueError(f"not an amount: {value!r}")
        try:
            d = Decimal(m.group(1).replace(",", ""))
        except InvalidOperation as e:
            raise ValueError(f"not an amount: {value!r}") from e
    return int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def fmt(sen: int, currency: str = "RM") -> str:
    sign = "-" if sen < 0 else ""
    sen = abs(sen)
    return f"{sign}{currency}{sen // 100:,}.{sen % 100:02d}"


def split_even(total_sen: int, n: int) -> list[int]:
    """Split so the parts add up exactly; leftover sen go to the first parts."""
    base, rem = divmod(total_sen, n)
    return [base + (1 if i < rem else 0) for i in range(n)]


def split_ratio(total_sen: int, ratio: list[int | float]) -> list[int]:
    """Split by ratio (e.g. [2, 1]); parts add up exactly."""
    if not ratio or any(r < 0 for r in ratio) or sum(ratio) == 0:
        raise ValueError(f"bad ratio: {ratio!r}")
    s = sum(ratio)
    parts = [int(total_sen * r // s) for r in ratio]
    for i in range(total_sen - sum(parts)):
        parts[i % len(parts)] += 1
    return parts

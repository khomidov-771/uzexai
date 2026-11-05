from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def format_number(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "—"
    try:
        number = Decimal(str(value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    except Exception:
        return str(value)
    if decimals == 0:
        raw = f"{number:.0f}"
    else:
        raw = f"{number:.{decimals}f}"
    integer, _, fraction = raw.partition(".")
    sign = ""
    if integer.startswith("-"):
        sign, integer = "-", integer[1:]
    groups: list[str] = []
    while integer:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    result = sign + " ".join(groups)
    return result + (f",{fraction}" if decimals else "")


def format_date(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (datetime, date)):
        return value.strftime("%d.%m.%Y")
    return str(value)


def currency_label(mode: str, language: str) -> str:
    if mode == "usd":
        return "USD" if language == "ru" else "AQSh dollari"
    return "сум" if language == "ru" else "so‘m"


def safe_text(value: Any) -> str:
    return str(value).replace("<", "&lt;").replace(">", "&gt;")


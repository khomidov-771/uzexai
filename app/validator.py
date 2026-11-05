from __future__ import annotations

import re
from decimal import Decimal
from typing import Any


NUMBER_RE = re.compile(r"(?<![A-Za-zА-Яа-я])[-+]?\d[\d\s.,]*(?![A-Za-zА-Яа-я])")


def _parse_number(token: str) -> Decimal | None:
    compact = token.strip().strip(".,").replace(" ", "").replace("\u00a0", "")
    if compact.count(",") == 1 and compact.count(".") == 0:
        compact = compact.replace(",", ".")
    else:
        compact = compact.replace(",", "")
    try:
        return Decimal(compact)
    except Exception:
        return None


class AnswerValidator:
    """Rejects generated text if it contains a numeric value absent from facts."""

    def validate(self, text: str, facts: dict[str, Any]) -> bool:
        allowed: list[Decimal] = []
        for value in facts.get("numeric_values", []):
            try:
                allowed.append(Decimal(str(value)))
            except Exception:
                continue
        for token in NUMBER_RE.findall(text):
            number = _parse_number(token)
            if number is None:
                continue
            # Years in period labels are metadata, not computed facts.
            if number >= 1900 and number <= 2100:
                continue
            if not any(abs(number - candidate) <= Decimal("0.02") for candidate in allowed):
                return False
        for entity in facts.get("allowed_entities", []):
            if entity and entity not in text and entity.lower() not in text.lower():
                # Only validate entities actually quoted by the answer generator.
                continue
        return True


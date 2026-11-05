from __future__ import annotations

import re
import unicodedata


_CYR_TO_LAT = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "ғ": "g", "д": "d", "е": "e",
        "ё": "yo", "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "қ": "q",
        "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s",
        "т": "t", "у": "u", "ў": "o", "ф": "f", "х": "x", "ҳ": "h", "ц": "ts",
        "ч": "ch", "ш": "sh", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
        "я": "ya",
    }
)


def transliterate_cyrillic(value: str) -> str:
    value = value.lower()
    return value.translate(_CYR_TO_LAT)


def normalize_text(value: str | None) -> str:
    """Canonical form for Uzbek/Russian Latin/Cyrillic entity matching."""
    if not value:
        return ""
    text = unicodedata.normalize("NFC", str(value)).lower()
    text = text.replace("o‘", "o").replace("o'", "o").replace("o`", "o")
    text = text.replace("g‘", "g").replace("g'", "g").replace("g`", "g")
    text = text.translate(_CYR_TO_LAT)
    text = text.replace("ў", "o").replace("қ", "q").replace("ғ", "g").replace("ҳ", "h")
    text = re.sub(r"[ʻʼ'’`´]", "", text)
    text = re.sub(
        r"\b(mchj|мчж|ooo|ооо|xk|хк|aj|аж|ao|ао|ok|чп|masuliyati cheklangan jamiyati)\b",
        " ",
        text,
    )
    text = re.sub(r"[\"«»“”()\[\]{},.;:/\\_\-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def number_normalize(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\D", "", str(value))


def compact_product(value: str | None) -> str:
    text = normalize_text(value)
    replacements = {
        "второи сорт": "2 сорт",
        "второй сорт": "2 сорт",
        "первый сорт": "1 сорт",
        "третьи сорт": "3 сорт",
        "третьи": "3",
        "хлопок сырец": "хлопок сырец",
    }
    for old, new in replacements.items():
        text = text.replace(normalize_text(old), normalize_text(new))
    return re.sub(r"\bсорт(?:а)?\b", "сорт", text)


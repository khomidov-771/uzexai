from __future__ import annotations

import re

from .schemas import Language


def detect_language(question: str) -> Language:
    text = question.lower()
    if re.search(r"[ўқғҳ]", text) or re.search(r"\b(қанча|бўйича|битим|маълумот|топилмади)\b", text):
        return Language.UZ
    if re.search(r"[а-яё]", text):
        uz_markers = (" qancha", " bo‘yicha", " bo'yicha", " bitim", " jami", " savdo", " so‘m", " so'm")
        if any(marker in f" {text}" for marker in uz_markers):
            return Language.UZ
        return Language.RU
    return Language.UZ


def language_script(question: str) -> str:
    if re.search(r"[ўқғҳ]", question.lower()):
        return "cyrillic"
    if re.search(r"[а-яё]", question.lower()):
        return "cyrillic"
    return "latin"


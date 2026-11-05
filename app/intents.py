from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Any

from .language import detect_language
from .normalization import number_normalize
from .schemas import Intent, Language, QueryPlan


MONTHS = {
    "yanvar": 1, "январь": 1, "января": 1, "январе": 1,
    "fevral": 2, "февраль": 2, "февраля": 2, "феврале": 2,
    "mart": 3, "март": 3, "марта": 3, "марте": 3,
    "aprel": 4, "апрель": 4, "апреля": 4, "апреле": 4,
    "may": 5, "май": 5, "мая": 5, "мае": 5,
    "iyun": 6, "июнь": 6, "июня": 6, "июне": 6,
    "iyul": 7, "июль": 7, "июля": 7, "июле": 7,
    "avgust": 8, "август": 8, "августа": 8, "августе": 8,
    "sentabr": 9, "сентябрь": 9, "сентября": 9, "сентябре": 9,
    "oktabr": 10, "октябрь": 10, "октября": 10, "октябре": 10,
    "noyabr": 11, "ноябрь": 11, "ноября": 11, "ноябре": 11,
    "dekabr": 12, "декабрь": 12, "декабря": 12, "декабре": 12,
}


def _last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _period(start: date, end: date, label: str) -> tuple[str, str, str]:
    return start.isoformat(), end.isoformat(), label


def parse_period(question: str, anchor: date, min_date: date, max_date: date) -> tuple[str | None, str | None, str]:
    text = question.lower()
    exact_dates = re.findall(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", text)
    if len(exact_dates) >= 2:
        try:
            values = [date(int(y), int(m), int(d)) for d, m, y in exact_dates[:2]]
        except ValueError:
            return None, None, "sana formati noto‘g‘ri"
        start, end = sorted(values)
        return _period(start, end, f"{start:%d.%m.%Y} — {end:%d.%m.%Y}")
    if len(exact_dates) == 1:
        d, m, y = exact_dates[0]
        try:
            target = date(int(y), int(m), int(d))
        except ValueError:
            return None, None, "sana formati noto‘g‘ri"
        return _period(target, target, f"{target:%d.%m.%Y}")
    year_match = re.search(r"\b(20\d{2})\b", text)
    year = int(year_match.group(1)) if year_match else anchor.year
    quarter_match = re.search(r"(?:\b([1-4])\s*(?:-?chorak|квартал)|(?:chorak|квартал)\s*([1-4]))", text)
    if quarter_match:
        quarter = int(quarter_match.group(1) or quarter_match.group(2))
        start_month = quarter * 3 - 2
        start, end = date(year, start_month, 1), _last_day(year, start_month + 2)
        return _period(start, end, f"{year}-yil {quarter}-chorak")
    month_match = next((name for name in MONTHS if re.search(rf"\b{re.escape(name)}\b", text)), None)
    if month_match:
        month = MONTHS[month_match]
        start, end = date(year, month, 1), _last_day(year, month)
        return _period(start, end, f"{year}-yil {month}-oy")
    if re.search(r"(?:so['’`]?nggi|последн(?:ие|их)|last)\s+(\d+)\s+(?:oy|месяц|month)", text):
        count = int(re.search(r"(?:so['’`]?nggi|последн(?:ие|их)|last)\s+(\d+)", text).group(1))
        end = anchor
        month_index = end.year * 12 + end.month - count
        start = date(month_index // 12, month_index % 12 + 1, 1)
        return _period(start, end, f"oxirgi {count} oy")
    if re.search(r"(?:o['’`]?tgan|прошл(?:ый|ом)|last)\s+(?:oy|месяц|month)", text):
        month_index = anchor.year * 12 + anchor.month - 2
        start = date(month_index // 12, month_index % 12 + 1, 1)
        return _period(start, _last_day(start.year, start.month), "o‘tgan oy")
    if re.search(r"(?:bu|joriy|этот|текущ(?:ий|ем))\s+(?:yil|год)", text):
        return _period(date(anchor.year, 1, 1), anchor, f"{anchor.year}-yil")
    if re.search(r"(?:o['’`]?tgan|прошл(?:ый|ом))\s+(?:yil|год)", text):
        return _period(date(anchor.year - 1, 1, 1), date(anchor.year - 1, 12, 31), f"{anchor.year - 1}-yil")
    if year_match:
        return _period(date(year, 1, 1), date(year, 12, 31), f"{year}-yil")
    return None, None, f"{min_date:%d.%m.%Y} — {max_date:%d.%m.%Y} (barcha mavjud ma’lumotlar)"


def _has(text: str, *phrases: str) -> bool:
    return any(phrase in text for phrase in phrases)


def parse_plan(question: str, min_date: date, max_date: date) -> QueryPlan:
    lang = detect_language(question)
    text = question.lower()
    start, end, period_label = parse_period(question, max_date, min_date, max_date)
    plan = QueryPlan(
        language=lang,
        intent=Intent.UNKNOWN,
        period_start=start,
        period_end=end,
        period_label=period_label,
        period_error=period_label == "sana formati noto‘g‘ri",
    )

    inn_match = re.search(r"(?<!\d)(\d{9})(?!\d)", question)
    if inn_match:
        plan.company_inn = number_normalize(inn_match.group(1))
    contract_match = re.search(r"(?:контракт|contract|shartnoma)\D{0,10}(\d{5,})", text)
    if contract_match:
        plan.contract_id = contract_match.group(1)
    deal_match = re.search(r"(?:сделк\w*|bitim\w*)\D{0,10}(\d{5,})", text)
    if deal_match:
        plan.deal_id = deal_match.group(1)

    plan.trade_type = "Экспортный" if _has(text, "eksport", "экспорт", "export") else None
    if _has(text, "annul", "аннулирован", "bekor qilingan", "bekor qilingan"):
        plan.statuses = ["Аннулирован(Не оплачен)"]
        plan.explicit_status_filter = True
    elif _has(text, "ijro etilgan", "исполнен", "исполненные", "bajarilgan"):
        plan.statuses = ["Исполнен", "Исполнен(Частично)"]
        plan.explicit_status_filter = True
    elif _has(text, "to‘langan", "to'langan", "оплачен", "оплаченные"):
        plan.statuses = ["Оплачен", "Исполнен", "Исполнен(Частично)"]
        plan.explicit_status_filter = True
    elif _has(text, "tuzilgan", "заключен", "заключенные"):
        plan.statuses = ["Заключен", "Ждёт оплату", "Оплачен", "Исполнен", "Исполнен(Частично)", "Аннулирован(Не оплачен)"]
        plan.explicit_status_filter = True

    if _has(text, "kurs", "курс", "usd", "доллар", "dollar") and not _has(text, "summasi", "сумма", "hajm", "объем"):
        plan.intent = Intent.EXCHANGE_RATE
        return plan
    if _has(text, "taqqosla", "сравни", "сравнение", "compare"):
        plan.intent = Intent.COMPARE
        if not plan.explicit_status_filter:
            plan.exclude_annulled = True
        return plan
    if _has(text, "top", "топ", "eng ko‘p", "eng kop", "рейтин", "лидер", "самые", "лучшие"):
        plan.intent = Intent.TOP
        plan.limit = _parse_limit(text)
        if not plan.explicit_status_filter:
            plan.exclude_annulled = True
        if _has(text, "tovar", "товар", "mahsulot", "продукт"):
            plan.group_by = "product"
        elif _has(text, "region", "viloyat", "регион", "област"):
            plan.group_by = "region"
        elif _has(text, "broker", "брокер"):
            plan.group_by = "broker"
        elif _has(text, "holat", "состояни", "status"):
            plan.group_by = "status"
        else:
            plan.group_by = "company"
        plan.metric = "amount_uzs"
        return plan
    if _has(text, "holat", "состояни", "статус", "status", "statuslar", "taqsimot", "распредел"):
        plan.intent = Intent.STATUS
        return plan
    if _has(text, "oxirgi bitim", "последняя сделка", "последний договор", "eng so‘nggi", "eng songgi"):
        plan.intent = Intent.LATEST
        return plan
    if plan.contract_id:
        plan.intent = Intent.CONTRACT
        return plan
    if _has(text, "profil", "rekvizit", "kim", "ma'lumot", "ma’lumot", "кто такой", "карточк") and (plan.company_inn or _has(text, "kompaniya", "компани")):
        plan.intent = Intent.COMPANY
        if not plan.explicit_status_filter:
            plan.exclude_annulled = True
        return plan
    if _has(text, "necha bitim", "nechta bitim", "bitimlar soni", "сделок", "количество сделок", "сколько сдел"):
        plan.intent = Intent.COUNT
        plan.metric = "count"
    elif _has(text, "hajm", "объем", "количество товара", "necha birlik", "qancha mahsulot"):
        plan.intent = Intent.VOLUME
        plan.metric = "volume"
    elif _has(text, "o‘rtacha narx", "o'rtacha narx", "средняя цена", "average price"):
        plan.intent = Intent.PRODUCT
        plan.metric = "unit_price"
    elif _has(text, "eng arzon", "минимальн", "min narx", "минимальная цена"):
        plan.intent = Intent.PRODUCT
        plan.metric = "min_price"
    elif _has(text, "eng qimmat", "максимальн", "max narx", "максимальная цена"):
        plan.intent = Intent.PRODUCT
        plan.metric = "max_price"
    elif _has(text, "narx", "цена", "price"):
        plan.intent = Intent.PRODUCT
        plan.metric = "unit_price"
    elif _has(text, "eksport", "экспорт", "export"):
        plan.intent = Intent.EXPORT
        plan.metric = "amount_uzs" if _has(text, "so‘m", "so'm", "сум", "ekvivalent") else "amount"
        plan.currency_mode = "uzs" if plan.metric == "amount_uzs" else "usd"
    elif _has(text, "jami", "сумма", "общая", "total", "daromad", "стоимость"):
        plan.intent = Intent.SUMMARY
        plan.metric = "amount_uzs"
    elif plan.company_inn or _has(text, "kompaniya", "компани"):
        plan.intent = Intent.COMPANY
    elif _has(text, "tovar", "товар", "mahsulot", "продукт"):
        plan.intent = Intent.PRODUCT
        plan.metric = "amount_uzs"
    else:
        plan.intent = Intent.UNKNOWN

    if plan.intent in {Intent.SUMMARY, Intent.VOLUME, Intent.PRODUCT, Intent.EXPORT} and not plan.explicit_status_filter:
        plan.exclude_annulled = True
    if plan.intent == Intent.EXPORT and plan.trade_type is None:
        plan.trade_type = "Экспортный"
    return plan


def _parse_limit(text: str) -> int:
    match = re.search(r"(?:top|топ|первых|birinchi)[\s-]*(\d+)", text)
    if not match:
        return 10
    return max(1, min(20, int(match.group(1))))


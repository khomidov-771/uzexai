from datetime import date

from app.intents import parse_period, parse_plan
from app.language import detect_language
from app.normalization import normalize_text
from app.schemas import Intent, Language
from app.validator import AnswerValidator


def test_normalization_handles_cyrillic_and_quotes():
    assert normalize_text('"ҲАРАЙЎМ КИМЁ" МЧЖ') == "harayom kimyo"


def test_language_detection():
    assert detect_language("2025-yilda jami summa qancha?") == Language.UZ
    assert detect_language("Сколько сделок в 2025 году?") == Language.RU
    assert detect_language("2025 йилда қанча битим?") == Language.UZ


def test_period_year():
    start, end, _ = parse_period("2024-yilda", date(2026, 10, 30), date(2022, 1, 3), date(2026, 10, 30))
    assert start == "2024-01-01"
    assert end == "2024-12-31"


def test_plan_summary_excludes_annulled():
    plan = parse_plan("2025-yilda jami summa qancha?", date(2022, 1, 3), date(2026, 10, 30))
    assert plan.intent == Intent.SUMMARY
    assert plan.exclude_annulled is True


def test_overview_range_and_bilingual_mode():
    plan = parse_plan("2022 yildan 2026 yilgacha barcha statistikani o‘zbek va rus tillarida ber", date(2022, 1, 3), date(2026, 10, 30))
    assert plan.intent == Intent.OVERVIEW
    assert plan.period_start == "2022-01-01"
    assert plan.period_end == "2026-12-31"
    assert plan.bilingual is True


def test_russian_full_statistics_is_overview():
    plan = parse_plan("Дайте полную статистику с 2022 по 2026 год", date(2022, 1, 3), date(2026, 10, 30))
    assert plan.intent == Intent.OVERVIEW
    assert plan.language == Language.RU


def test_validator_rejects_unknown_number():
    validator = AnswerValidator()
    assert validator.validate("Jami 1 234 so‘m.", {"numeric_values": [1234]})
    assert not validator.validate("Jami 9 999 so‘m.", {"numeric_values": [1234]})


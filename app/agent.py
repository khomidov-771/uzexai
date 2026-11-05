from __future__ import annotations

import json
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .db import Database
from .formatting import currency_label, format_date, format_number
from .intents import parse_plan
from .normalization import normalize_text
from .ollama import OllamaPlanner
from .schemas import AgentResponse, Intent, Language, QueryPlan
from .validator import AnswerValidator


ANNULLED = "Аннулирован(Не оплачен)"


class EvidenceAgent:
    """Deterministic analytics agent with an optional constrained Ollama planner."""

    def __init__(self, db: Database, *, ollama: OllamaPlanner | None = None, log_path: str | Path | None = None):
        self.db = db
        self.ollama = ollama
        self.validator = AnswerValidator()
        self.log_path = Path(log_path) if log_path else None
        stats = db.table_stats()
        self.min_date = _as_date(stats.get("min_date"))
        self.max_date = _as_date(stats.get("max_date"))
        self._participants = db.query("SELECT inn, name, region FROM participants WHERE inn IS NOT NULL")
        self._products = db.query(
            "SELECT DISTINCT COALESCE(NULLIF(contract_product, ''), product) AS value FROM deals_enriched WHERE COALESCE(NULLIF(contract_product, ''), product) IS NOT NULL"
        )
        self._regions = db.query("SELECT DISTINCT region AS value FROM deals_enriched WHERE region IS NOT NULL")
        self._brokers = db.query("SELECT broker_code, name FROM brokers")

    def ask(self, question: str) -> AgentResponse:
        started = time.perf_counter()
        question = question.strip()
        if not question:
            return AgentResponse(
                answer="Savol bo‘sh. Masalan: 2025-yilda jami bitimlar summasi qancha?",
                intent=Intent.UNKNOWN.value,
                language=Language.UZ.value,
                safe=True,
            )
        plan = parse_plan(question, self.min_date, self.max_date)
        if plan.intent == Intent.UNKNOWN and self.ollama:
            hint = self.ollama.plan(question)
            if hint:
                plan = self.ollama.apply_hint(plan, hint)
        if plan.period_error:
            message = "Sana formati noto‘g‘ri. DD.MM.YYYY ko‘rinishida kiriting." if plan.language == Language.UZ else "Неверный формат даты. Используйте DD.MM.YYYY."
            response = self._simple_response(message, plan)
            return self._finish(question, response, started)
        missing = self._resolve_entities(plan, question)
        if missing:
            response = self._simple_response(missing, plan)
            return self._finish(question, response, started)
        if plan.period_start and plan.period_end:
            start = date.fromisoformat(plan.period_start)
            end = date.fromisoformat(plan.period_end)
            if end < self.min_date or start > self.max_date:
                response = self._simple_response(self._not_available_period(plan), plan)
                return self._finish(question, response, started)
        if self._unsupported_field(question):
            response = self._simple_response(self._unsupported_answer(plan), plan)
            return self._finish(question, response, started)
        if plan.intent == Intent.UNKNOWN:
            response = self._simple_response(self._unknown_answer(plan), plan)
            return self._finish(question, response, started)
        try:
            response = self._execute(plan, question)
        except Exception as exc:  # Safe user-facing fallback; details are logged.
            response = self._simple_response(self._technical_fallback(plan), plan)
            response.evidence["error"] = type(exc).__name__
        return self._finish(question, response, started)

    def _finish(self, question: str, response: AgentResponse, started: float) -> AgentResponse:
        response.latency_ms = round((time.perf_counter() - started) * 1000, 2)
        self._log(question, response)
        return response

    def _resolve_entities(self, plan: QueryPlan, question: str) -> str | None:
        if plan.company_inn:
            row = next((item for item in self._participants if str(item.get("inn")) == plan.company_inn), None)
            if not row:
                return self._not_found_entity(plan.company_inn, "INN", plan.language)
            plan.company_name = row.get("name")
        quoted = re.findall(r"[«“\"]([^»”\"]+)[»”\"]", question)
        if quoted and not plan.company_inn:
            wanted = normalize_text(quoted[0])
            company = self._best_entity(wanted, self._participants, "name", threshold=0.90)
            if company:
                plan.company_inn = str(company.get("inn"))
                plan.company_name = company.get("name")
            elif _looks_like_company_question(question):
                return self._not_found_entity(quoted[0], "company", plan.language)
        if not plan.company_inn and (plan.intent == Intent.COMPANY or "mchj" in question.lower() or "мчж" in question.lower()):
            company = self._best_entity(normalize_text(question), self._participants, "name", threshold=0.92, substring=True)
            if company:
                plan.company_inn = str(company.get("inn"))
                plan.company_name = company.get("name")

        if plan.intent in {Intent.SUMMARY, Intent.COUNT, Intent.VOLUME, Intent.PRODUCT, Intent.EXPORT, Intent.TOP}:
            product = self._find_product(question, plan)
            if product:
                plan.product = product
            elif quoted and _looks_like_product_question(question):
                return self._not_found_entity(quoted[0], "product", plan.language)

        region = self._best_entity(normalize_text(question), self._regions, "value", threshold=0.98, substring=True)
        if region and _looks_like_region_question(question):
            plan.region = region.get("value")

        broker_match = re.search(r"\b(BK\d{3})\b", question, flags=re.IGNORECASE)
        if broker_match:
            code = broker_match.group(1).upper()
            if any(item.get("broker_code") == code for item in self._brokers):
                plan.broker_code = code
            else:
                return self._not_found_entity(code, "broker", plan.language)
        elif any(token in question.lower() for token in ("broker", "брокер")):
            broker = self._best_entity(normalize_text(question), self._brokers, "name", threshold=0.92, substring=True)
            if broker:
                plan.broker_code = broker.get("broker_code")
        return None

    def _find_product(self, question: str, plan: QueryPlan) -> str | None:
        text = normalize_text(question)
        if plan.group_by == "product" and not _has_specific_product_marker(question):
            return None
        exact = next(
            (
                item
                for item in self._products
                if len(normalize_text(item.get("value"))) >= 4
                and normalize_text(item.get("value")) in text
            ),
            None,
        )
        if exact:
            return exact.get("value")
        # Fuzzy linking is deliberately conservative: at least one meaningful token must overlap.
        candidates: list[tuple[float, str]] = []
        try:
            from rapidfuzz import fuzz
        except ImportError:
            fuzz = None
        for item in self._products:
            value = item.get("value")
            normalized = normalize_text(value)
            if not value or len(normalized) < 5:
                continue
            tokens = [token for token in normalized.split() if len(token) >= 5]
            overlap = any(token in text for token in tokens)
            if not overlap:
                continue
            score = fuzz.token_set_ratio(normalized, text) / 100 if fuzz else 0.0
            if score >= 0.90:
                candidates.append((score, value))
        return max(candidates, default=(0.0, None))[1]

    def _best_entity(self, wanted: str, rows: list[dict[str, Any]], key: str, threshold: float, substring: bool = False) -> dict[str, Any] | None:
        if not wanted:
            return None
        compact = wanted.replace(" ", "")
        for row in rows:
            value = row.get(key)
            normalized = normalize_text(value)
            if not normalized:
                continue
            if substring and (normalized in wanted or normalized.replace(" ", "") in compact):
                return row
            if not substring and normalized in wanted:
                return row
        if substring:
            try:
                from rapidfuzz import fuzz, process
                choices = {normalize_text(row.get(key)): row for row in rows if row.get(key)}
                match = process.extractOne(wanted, list(choices), scorer=fuzz.token_set_ratio)
                if match and match[1] / 100 >= threshold:
                    return choices[match[0]]
            except ImportError:
                pass
        return None

    def _execute(self, plan: QueryPlan, question: str) -> AgentResponse:
        if plan.intent == Intent.EXCHANGE_RATE:
            return self._exchange_rate(plan)
        clauses, params = self._where(plan)
        where_sql = " AND ".join(clauses)
        if plan.intent == Intent.SUMMARY:
            row = self.db.one(
                f"SELECT COUNT(*) AS deal_count, COALESCE(SUM(amount_uzs), 0) AS amount_uzs, COALESCE(SUM(volume), 0) AS volume FROM deals_enriched WHERE {where_sql}",
                params,
            ) or {}
            return self._summary_response(plan, row)
        if plan.intent == Intent.COUNT:
            row = self.db.one(f"SELECT COUNT(*) AS deal_count FROM deals_enriched WHERE {where_sql}", params) or {}
            return self._count_response(plan, row)
        if plan.intent == Intent.VOLUME:
            row = self.db.one(f"SELECT COUNT(*) AS deal_count, COALESCE(SUM(volume), 0) AS volume FROM deals_enriched WHERE {where_sql}", params) or {}
            return self._volume_response(plan, row)
        if plan.intent == Intent.PRODUCT:
            row = self.db.one(
                f"SELECT COUNT(*) AS deal_count, AVG(unit_price) AS average_price, MIN(unit_price) AS min_price, MAX(unit_price) AS max_price FROM deals_enriched WHERE {where_sql}",
                params,
            ) or {}
            return self._product_response(plan, row)
        if plan.intent == Intent.EXPORT:
            row = self.db.one(
                f"SELECT COUNT(*) AS deal_count, COALESCE(SUM(amount), 0) AS amount_raw, COALESCE(SUM(amount_uzs), 0) AS amount_uzs FROM deals_enriched WHERE {where_sql}",
                params,
            ) or {}
            return self._export_response(plan, row)
        if plan.intent == Intent.TOP:
            return self._top_response(plan, where_sql, params)
        if plan.intent == Intent.STATUS:
            return self._status_response(plan, where_sql, params)
        if plan.intent == Intent.COMPANY:
            return self._company_response(plan, where_sql, params)
        if plan.intent == Intent.CONTRACT:
            return self._contract_response(plan, where_sql, params)
        if plan.intent == Intent.LATEST:
            return self._latest_response(plan, where_sql, params)
        if plan.intent == Intent.COMPARE:
            return self._compare_response(plan, question)
        return self._simple_response(self._unknown_answer(plan), plan)

    def _where(self, plan: QueryPlan) -> tuple[list[str], list[Any]]:
        clauses = ["1=1"]
        params: list[Any] = []
        if plan.period_start and plan.period_end:
            clauses.append("deal_date BETWEEN ? AND ?")
            params.extend([plan.period_start, plan.period_end])
        if plan.statuses:
            marks = ", ".join("?" for _ in plan.statuses)
            clauses.append(f"status IN ({marks})")
            params.extend(plan.statuses)
        elif plan.exclude_annulled:
            clauses.append("status <> ?")
            params.append(ANNULLED)
        if plan.company_inn:
            clauses.append("(seller_inn = ? OR buyer_inn = ?)")
            params.extend([plan.company_inn, plan.company_inn])
        if plan.product:
            clauses.append("COALESCE(contract_product, product) ILIKE ?")
            params.append(f"%{plan.product}%")
        if plan.region:
            clauses.append("region ILIKE ?")
            params.append(f"%{plan.region}%")
        if plan.broker_code:
            clauses.append("(seller_broker = ? OR buyer_broker = ?)")
            params.extend([plan.broker_code, plan.broker_code])
        if plan.trade_type:
            # In the source CSV auction type is `Тип торгов`, while internal/export
            # is `Тип контракта`.
            clauses.append("contract_type = ?" if plan.trade_type == "Экспортный" else "trade_type = ?")
            params.append(plan.trade_type)
        if plan.contract_id:
            clauses.append("contract_id = ?")
            params.append(int(plan.contract_id))
        if plan.deal_id:
            clauses.append("deal_id = ?")
            params.append(int(plan.deal_id))
        return clauses, params

    def _exchange_rate(self, plan: QueryPlan) -> AgentResponse:
        target = plan.period_start or self.max_date.isoformat()
        row = self.db.one("SELECT rate_date, usd_rate FROM usd_rates WHERE rate_date <= ? ORDER BY rate_date DESC LIMIT 1", [target]) or {}
        if not row:
            return self._simple_response(self._no_result_answer(plan), plan)
        rate = row.get("usd_rate")
        facts = self._facts([rate, 1], entities=[])
        if plan.language == Language.RU:
            answer = f"Курс USD на {format_date(row.get('rate_date'))}: {format_number(rate, 2)} сум за 1 USD."
        else:
            answer = f"{format_date(row.get('rate_date'))} sanasidagi USD kursi: {format_number(rate, 2)} so‘m / 1 USD."
        return self._validated(answer, Intent.EXCHANGE_RATE, plan, facts, row, "SELECT rate_date, usd_rate FROM usd_rates WHERE rate_date <= ? ORDER BY rate_date DESC LIMIT 1", [target])

    def _summary_response(self, plan: QueryPlan, row: dict[str, Any]) -> AgentResponse:
        amount = row.get("amount_uzs", 0) or 0
        count = row.get("deal_count", 0) or 0
        if count == 0:
            return self._no_result(plan)
        facts = self._facts([amount, count], [plan.company_name] if plan.company_name else [])
        cur = currency_label("uzs", plan.language.value)
        if plan.language == Language.RU:
            answer = f"За {plan.period_label} общая сумма сделок: {format_number(amount)} {cur} ({format_number(count, 0)} сделок)."
            answer += f" Фильтр статуса: {self._status_label(plan, 'ru')}."
        else:
            answer = f"{plan.period_label} davrida jami bitimlar summasi: {format_number(amount)} {cur} ({format_number(count, 0)} ta bitim)."
            answer += f" Holat filtri: {self._status_label(plan, 'uz')}."
        answer += self._source_line(plan, count, plan.language)
        return self._validated(answer, Intent.SUMMARY, plan, facts, row)

    def _count_response(self, plan: QueryPlan, row: dict[str, Any]) -> AgentResponse:
        count = row.get("deal_count", 0) or 0
        if count == 0:
            return self._no_result(plan)
        facts = self._facts([count], [])
        if plan.language == Language.RU:
            answer = f"За {plan.period_label} найдено {format_number(count, 0)} сделок. Фильтр статуса: {self._status_label(plan, 'ru')}."
        else:
            answer = f"{plan.period_label} davrida {format_number(count, 0)} ta bitim topildi. Holat filtri: {self._status_label(plan, 'uz')}."
        answer += self._source_line(plan, count, plan.language)
        return self._validated(answer, Intent.COUNT, plan, facts, row)

    def _volume_response(self, plan: QueryPlan, row: dict[str, Any]) -> AgentResponse:
        volume, count = row.get("volume", 0) or 0, row.get("deal_count", 0) or 0
        if count == 0:
            return self._no_result(plan)
        facts = self._facts([volume, count], [])
        if plan.language == Language.RU:
            answer = f"Объём за {plan.period_label}: {format_number(volume)} единиц ({format_number(count, 0)} сделок)."
        else:
            answer = f"{plan.period_label} davridagi hajm: {format_number(volume)} birlik ({format_number(count, 0)} ta bitim)."
        answer += self._source_line(plan, count, plan.language)
        return self._validated(answer, Intent.VOLUME, plan, facts, row)

    def _product_response(self, plan: QueryPlan, row: dict[str, Any]) -> AgentResponse:
        count = row.get("deal_count", 0) or 0
        avg = row.get("average_price")
        low = row.get("min_price")
        high = row.get("max_price")
        facts = self._facts([count, avg, low, high], [plan.product] if plan.product else [])
        if avg is None:
            return self._no_result(plan)
        if plan.language == Language.RU:
            answer = f"Средняя цена за {plan.period_label}: {format_number(avg)} (минимум {format_number(low)}, максимум {format_number(high)}; {format_number(count, 0)} сделок)."
        else:
            answer = f"{plan.period_label} davrida o‘rtacha narx: {format_number(avg)} (minimum {format_number(low)}, maksimum {format_number(high)}; {format_number(count, 0)} ta bitim)."
        answer += self._source_line(plan, count, plan.language)
        return self._validated(answer, Intent.PRODUCT, plan, facts, row)

    def _export_response(self, plan: QueryPlan, row: dict[str, Any]) -> AgentResponse:
        count = row.get("deal_count", 0) or 0
        raw = row.get("amount_raw", 0) or 0
        uzs = row.get("amount_uzs", 0) or 0
        if count == 0:
            return self._no_result(plan)
        facts = self._facts([count, raw, uzs], [])
        if plan.currency_mode == "usd":
            amount, label = raw, "USD"
        else:
            amount, label = uzs, "сум" if plan.language == Language.RU else "so‘m"
        if plan.language == Language.RU:
            answer = f"Экспортные сделки за {plan.period_label}: {format_number(amount)} {label} ({format_number(count, 0)} сделок)."
            if plan.currency_mode != "usd":
                answer += " Сумовый эквивалент рассчитан по курсу USD на дату каждой сделки."
        else:
            answer = f"{plan.period_label} eksport bitimlari: {format_number(amount)} {label} ({format_number(count, 0)} ta bitim)."
            if plan.currency_mode != "usd":
                answer += " So‘m ekvivalenti har bir bitim sanasidagi USD kursi bilan hisoblandi."
        answer += self._source_line(plan, count, plan.language)
        return self._validated(answer, Intent.EXPORT, plan, facts, row)

    def _top_response(self, plan: QueryPlan, where_sql: str, params: list[Any]) -> AgentResponse:
        group = plan.group_by or "company"
        expressions = {
            "product": ("COALESCE(contract_product, product)", "tovar"),
            "region": ("region", "region"),
            "broker": ("COALESCE(seller_broker_name, seller_broker)", "broker"),
            "status": ("status", "holat"),
            "month": ("strftime(deal_date, '%Y-%m')", "oy"),
            "company": ("COALESCE(seller_name, seller_inn)", "kompaniya"),
        }
        expression, label = expressions.get(group, expressions["company"])
        sql = f"SELECT {expression} AS label, COUNT(*) AS deal_count, SUM(amount_uzs) AS amount_uzs FROM deals_enriched WHERE {where_sql} GROUP BY 1 ORDER BY amount_uzs DESC NULLS LAST LIMIT ?"
        rows = self.db.query(sql, [*params, plan.limit])
        if not rows:
            return self._no_result(plan)
        values: list[Any] = []
        labels: list[str] = []
        for row in rows:
            values.extend([row.get("amount_uzs", 0), row.get("deal_count", 0)])
            if row.get("label"):
                labels.append(str(row["label"]))
        total_count = sum((r.get("deal_count", 0) or 0) for r in rows)
        lines = []
        for index, row in enumerate(rows, 1):
            values.append(index)
            lines.append(f"{index}) {row.get('label') or '—'} — {format_number(row.get('amount_uzs', 0))} {currency_label('uzs', plan.language.value)}; {format_number(row.get('deal_count', 0), 0)}")
        facts = self._facts([*values, plan.limit, len(rows), total_count], labels)
        if plan.language == Language.RU:
            answer = f"Топ-{len(rows)} по сумме за {plan.period_label}:\n" + "\n".join(lines)
        else:
            answer = f"{plan.period_label} bo‘yicha summa jihatidan top-{len(rows)} {label}:\n" + "\n".join(lines)
        answer += self._source_line(plan, sum((r.get("deal_count", 0) or 0) for r in rows), plan.language)
        return self._validated(answer, Intent.TOP, plan, facts, {"rows": rows}, sql, [*params, plan.limit])

    def _status_response(self, plan: QueryPlan, where_sql: str, params: list[Any]) -> AgentResponse:
        sql = f"SELECT status, COUNT(*) AS deal_count, SUM(amount_uzs) AS amount_uzs FROM deals_enriched WHERE {where_sql} GROUP BY status ORDER BY deal_count DESC"
        rows = self.db.query(sql, params)
        if not rows:
            return self._no_result(plan)
        total_count = sum((r.get("deal_count", 0) or 0) for r in rows)
        values = [value for row in rows for value in (row.get("deal_count", 0), row.get("amount_uzs", 0))]
        values.append(total_count)
        facts = self._facts(values, [row.get("status") for row in rows])
        lines = [f"{row.get('status') or '—'} — {format_number(row.get('deal_count', 0), 0)}" for row in rows]
        if plan.language == Language.RU:
            answer = f"Распределение статусов за {plan.period_label}:\n" + "\n".join(lines)
        else:
            answer = f"{plan.period_label} davridagi holatlar taqsimoti:\n" + "\n".join(lines)
        answer += self._source_line(plan, sum((r.get("deal_count", 0) or 0) for r in rows), plan.language)
        return self._validated(answer, Intent.STATUS, plan, facts, {"rows": rows}, sql, params)

    def _company_response(self, plan: QueryPlan, where_sql: str, params: list[Any]) -> AgentResponse:
        if not plan.company_inn:
            return self._simple_response(
                "Kompaniya nomi yoki 9 xonali INNni yozing." if plan.language == Language.UZ else "Укажите название компании или 9-значный ИНН.", plan
            )
        sql = f"SELECT COUNT(*) AS deal_count, COALESCE(SUM(amount_uzs), 0) AS amount_uzs, MIN(deal_date) AS first_date, MAX(deal_date) AS last_date FROM deals_enriched WHERE {where_sql}"
        row = self.db.one(sql, params) or {}
        count, amount = row.get("deal_count", 0) or 0, row.get("amount_uzs", 0) or 0
        facts = self._facts([count, amount, plan.company_inn], [plan.company_name] if plan.company_name else [])
        if plan.language == Language.RU:
            answer = f"Профиль {plan.company_name}: ИНН {plan.company_inn}; {format_number(count, 0)} сделок; сумма {format_number(amount)} сум; период сделок {format_date(row.get('first_date'))} — {format_date(row.get('last_date'))}."
        else:
            answer = f"{plan.company_name} profili: INN {plan.company_inn}; {format_number(count, 0)} ta bitim; summa {format_number(amount)} so‘m; bitimlar davri {format_date(row.get('first_date'))} — {format_date(row.get('last_date'))}."
        answer += self._source_line(plan, count, plan.language)
        return self._validated(answer, Intent.COMPANY, plan, facts, row, sql, params)

    def _contract_response(self, plan: QueryPlan, where_sql: str, params: list[Any]) -> AgentResponse:
        sql = f"SELECT contract_id, COALESCE(contract_product, product) AS product, COUNT(*) AS deal_count, SUM(amount_uzs) AS amount_uzs, MAX(status) AS last_status FROM deals_enriched WHERE {where_sql} GROUP BY contract_id, product"
        row = self.db.one(sql, params)
        if not row:
            return self._no_result(plan)
        facts = self._facts([row.get("contract_id"), row.get("deal_count", 0), row.get("amount_uzs", 0)], [row.get("product"), row.get("last_status")])
        if plan.language == Language.RU:
            answer = f"Контракт {row.get('contract_id')}: {row.get('product') or 'товар не указан'}; {format_number(row.get('deal_count', 0), 0)} сделок; сумма {format_number(row.get('amount_uzs', 0))} сум; статус: {row.get('last_status') or '—'}."
        else:
            answer = f"{row.get('contract_id')}-shartnoma: {row.get('product') or 'tovar ko‘rsatilmagan'}; {format_number(row.get('deal_count', 0), 0)} ta bitim; summa {format_number(row.get('amount_uzs', 0))} so‘m; holat: {row.get('last_status') or '—'}."
        return self._validated(answer, Intent.CONTRACT, plan, facts, row, sql, params)

    def _latest_response(self, plan: QueryPlan, where_sql: str, params: list[Any]) -> AgentResponse:
        sql = f"SELECT deal_id, deal_date, COALESCE(contract_product, product) AS product, amount_uzs, status FROM deals_enriched WHERE {where_sql} ORDER BY deal_date DESC, deal_time DESC LIMIT 1"
        row = self.db.one(sql, params)
        if not row:
            return self._no_result(plan)
        facts = self._facts([row.get("deal_id"), row.get("amount_uzs", 0)], [row.get("product"), row.get("status")])
        if plan.language == Language.RU:
            answer = f"Последняя сделка: №{row.get('deal_id')} от {format_date(row.get('deal_date'))}, {row.get('product') or 'товар не указан'}, {format_number(row.get('amount_uzs', 0))} сум, статус: {row.get('status') or '—'}."
        else:
            answer = f"Oxirgi bitim: №{row.get('deal_id')}, sana {format_date(row.get('deal_date'))}, {row.get('product') or 'tovar ko‘rsatilmagan'}, {format_number(row.get('amount_uzs', 0))} so‘m, holat: {row.get('status') or '—'}."
        return self._validated(answer, Intent.LATEST, plan, facts, row, sql, params)

    def _compare_response(self, plan: QueryPlan, question: str) -> AgentResponse:
        years = [int(value) for value in re.findall(r"\b(20\d{2})\b", question)]
        years = list(dict.fromkeys(years))[:2]
        if len(years) < 2:
            return self._simple_response(
                "Taqqoslash uchun ikki yilni ko‘rsating, masalan: 2024 va 2025." if plan.language == Language.UZ else "Укажите два года для сравнения, например: 2024 и 2025.", plan
            )
        clauses = ["EXTRACT(year FROM deal_date) IN (?, ?)"]
        params: list[Any] = years
        if plan.exclude_annulled:
            clauses.append("status <> ?")
            params.append(ANNULLED)
        sql = f"SELECT EXTRACT(year FROM deal_date) AS year, COUNT(*) AS deal_count, SUM(amount_uzs) AS amount_uzs FROM deals_enriched WHERE {' AND '.join(clauses)} GROUP BY 1 ORDER BY 1"
        rows = self.db.query(sql, params)
        if not rows:
            return self._no_result(plan)
        facts = self._facts([v for r in rows for v in (r.get("year"), r.get("deal_count", 0), r.get("amount_uzs", 0))], [])
        money_label = "сум" if plan.language == Language.RU else "so‘m"
        lines = [f"{int(row['year'])}: {format_number(row.get('amount_uzs', 0))} {money_label}; {format_number(row.get('deal_count', 0), 0)}" for row in rows]
        answer = ("Yillar taqqoslanishi:\n" if plan.language == Language.UZ else "Сравнение лет:\n") + "\n".join(lines)
        return self._validated(answer, Intent.COMPARE, plan, facts, {"rows": rows}, sql, params)

    def _validated(self, answer: str, intent: Intent, plan: QueryPlan, facts: dict[str, Any], row: Any, sql: str | None = None, params: list[Any] | None = None) -> AgentResponse:
        if not self.validator.validate(answer, facts):
            answer = self._safe_numeric_fallback(plan)
            return AgentResponse(answer=answer, intent=intent.value, language=plan.language.value, evidence={"validated": False, "reason": "numeric_mismatch"}, sql=sql, params=params or [], safe=True)
        evidence = {
            "validated": True,
            "period": plan.period_label,
            "status_filter": self._status_label(plan, plan.language.value),
            "currency": currency_label(plan.currency_mode, plan.language.value),
            "row_count": row.get("deal_count") if isinstance(row, dict) and "deal_count" in row else None,
            "source": "DuckDB + deterministic SQL template",
        }
        return AgentResponse(answer=answer, intent=intent.value, language=plan.language.value, evidence=evidence, sql=sql, params=params or [], safe=True)

    def _facts(self, values: list[Any], entities: list[Any]) -> dict[str, Any]:
        numeric_values = [v for v in values if v is not None]
        for entity in entities:
            numeric_values.extend(re.findall(r"\d+", str(entity)))
        return {"numeric_values": numeric_values, "allowed_entities": [e for e in entities if e]}

    def _simple_response(self, text: str, plan: QueryPlan) -> AgentResponse:
        return AgentResponse(answer=text, intent=plan.intent.value, language=plan.language.value, evidence={"validated": True}, safe=True)

    def _no_result(self, plan: QueryPlan) -> AgentResponse:
        return self._simple_response(self._no_result_answer(plan), plan)

    def _status_label(self, plan: QueryPlan, language: str) -> str:
        if plan.statuses:
            return ", ".join(plan.statuses)
        if plan.exclude_annulled:
            return "без аннулированных" if language == "ru" else "annullanganlarsiz"
        return "все статусы" if language == "ru" else "barcha holatlar"

    def _source_line(self, plan: QueryPlan, count: Any, language: Language) -> str:
        if language == Language.RU:
            return f"\nИсточник: {plan.period_label}; статус: {self._status_label(plan, 'ru')}; строк рассчитано: {format_number(count, 0)}."
        return f"\nManba: {plan.period_label}; holat: {self._status_label(plan, 'uz')}; hisoblangan qatorlar: {format_number(count, 0)}."

    def _safe_numeric_fallback(self, plan: QueryPlan) -> str:
        return "Natija hisoblandi, lekin raqamli tekshiruvdan o‘tmadi; xavfsizlik sababli raqam ko‘rsatilmaydi." if plan.language == Language.UZ else "Результат рассчитан, но не прошёл числовую проверку; цифры скрыты из соображений безопасности."

    def _not_found_entity(self, value: str, kind: str, language: Language) -> str:
        if language == Language.RU:
            return f"В данных не найден {kind}: «{value}». Чужую компанию или товар подставлять не буду."
        return f"Ma’lumotlarda {kind} topilmadi: «{value}». Boshqa kompaniya yoki tovarni taxmin qilib bermayman."

    def _not_available_period(self, plan: QueryPlan) -> str:
        if plan.language == Language.RU:
            return f"Запрошенный период не входит в набор данных. Доступный диапазон: {self.min_date:%d.%m.%Y} — {self.max_date:%d.%m.%Y}."
        return f"So‘ralgan davr ma’lumotlar to‘plamiga kirmaydi. Mavjud oraliq: {self.min_date:%d.%m.%Y} — {self.max_date:%d.%m.%Y}."

    def _unsupported_answer(self, plan: QueryPlan) -> str:
        if plan.language == Language.RU:
            return "Этот показатель отсутствует в базе. Доступны сделки, суммы, объёмы, цены, компании, товары, регионы, брокеры, статусы, контракты и курс USD."
        return "Bu ko‘rsatkich bazada mavjud emas. Bitimlar, summalar, hajm, narx, kompaniya, tovar, region, broker, holat, shartnoma va USD kursi bo‘yicha javob beraman."

    def _unknown_answer(self, plan: QueryPlan) -> str:
        if plan.language == Language.RU:
            return "Вопрос не удалось безопасно сопоставить с доступной аналитикой. Спросите о сумме, количестве, объёме, цене, топе, компании, контракте, статусе или курсе USD."
        return "Savolni mavjud analitika bilan xavfsiz bog‘lab bo‘lmadi. Summa, son, hajm, narx, top, kompaniya, shartnoma, holat yoki USD kursi haqida so‘rang."

    def _no_result_answer(self, plan: QueryPlan) -> str:
        if plan.language == Language.RU:
            return f"По заданным условиям сделки не найдены: {plan.period_label}."
        return f"Berilgan shartlar bo‘yicha bitimlar topilmadi: {plan.period_label}."

    def _technical_fallback(self, plan: QueryPlan) -> str:
        return "So‘rovni bajarishda texnik xatolik yuz berdi; xavfsizlik sababli taxminiy javob berilmadi." if plan.language == Language.UZ else "При выполнении запроса произошла техническая ошибка; предположительный ответ не выдан."

    def _unsupported_field(self, question: str) -> bool:
        return any(token in question.lower() for token in ("marja", "маржа", "yetkazib berish muddati", "срок поставки", "foyda", "прибыль"))

    def _log(self, question: str, response: AgentResponse) -> None:
        if not self.log_path:
            return
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"ts": datetime.now().isoformat(), "question": question, "response": response.answer, "intent": response.intent, "latency_ms": response.latency_ms, "safe": response.safe}, ensure_ascii=False) + "\n")
        except OSError:
            pass


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _looks_like_company_question(question: str) -> bool:
    text = question.lower()
    return any(token in text for token in ("kompaniya", "компани", "mchj", "мчж", "inn", "стир"))


def _looks_like_product_question(question: str) -> bool:
    text = question.lower()
    return any(token in text for token in ("tovar", "товар", "mahsulot", "продукт", "narx", "цена"))


def _has_specific_product_marker(question: str) -> bool:
    text = question.lower()
    return any(token in text for token in ("tovar ", "товар ", "mahsulot ", "продукт ", "narxi", "цена "))


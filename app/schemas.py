from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Language(StrEnum):
    UZ = "uz"
    RU = "ru"


class Intent(StrEnum):
    SUMMARY = "summary"
    COUNT = "count"
    VOLUME = "volume"
    TOP = "top"
    COMPANY = "company"
    PRODUCT = "product"
    CONTRACT = "contract"
    EXPORT = "export"
    STATUS = "status"
    EXCHANGE_RATE = "exchange_rate"
    LATEST = "latest"
    COMPARE = "compare"
    UNKNOWN = "unknown"


@dataclass
class QueryPlan:
    intent: Intent
    language: Language
    period_start: str | None = None
    period_end: str | None = None
    period_label: str = "barcha mavjud ma’lumotlar"
    period_error: bool = False
    metric: str = "amount_uzs"
    group_by: str | None = None
    limit: int = 10
    company_inn: str | None = None
    company_name: str | None = None
    product: str | None = None
    contract_id: str | None = None
    deal_id: str | None = None
    region: str | None = None
    broker_code: str | None = None
    trade_type: str | None = None
    statuses: list[str] = field(default_factory=list)
    exclude_annulled: bool = False
    explicit_status_filter: bool = False
    currency_mode: str = "uzs"
    source: str = "rules"


@dataclass
class AgentResponse:
    answer: str
    intent: str
    language: str
    evidence: dict[str, Any] = field(default_factory=dict)
    sql: str | None = None
    params: list[Any] = field(default_factory=list)
    safe: bool = True
    latency_ms: float = 0.0


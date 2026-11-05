from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .schemas import Intent, QueryPlan


class OllamaPlanner:
    """Optional constrained planner. It never receives raw rows and never executes SQL."""

    def __init__(self, base_url: str, model: str, timeout: float = 20):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def plan(self, question: str) -> dict[str, Any] | None:
        system = (
            "You are a query classifier for a fixed UZEX database. Return JSON only. "
            "Never invent numbers, names, dates, SQL, or facts. Choose one intent from: "
            "summary,count,volume,top,company,product,contract,export,status,exchange_rate,latest,compare,unknown. "
            "Keys: intent, metric, group_by, limit, period, entity. If uncertain use unknown."
        )
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": question},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            content = body.get("message", {}).get("content", "")
            result = json.loads(content)
            if not isinstance(result, dict) or result.get("intent") not in {item.value for item in Intent}:
                return None
            return result
        except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError):
            return None

    @staticmethod
    def apply_hint(plan: QueryPlan, hint: dict[str, Any]) -> QueryPlan:
        try:
            plan.intent = Intent(str(hint.get("intent", plan.intent.value)))
        except ValueError:
            return plan
        metric = hint.get("metric")
        if metric in {"amount_uzs", "amount", "count", "volume", "unit_price"}:
            plan.metric = metric
        group_by = hint.get("group_by")
        if group_by in {"product", "company", "region", "broker", "status", "month"}:
            plan.group_by = group_by
        try:
            plan.limit = max(1, min(20, int(hint.get("limit", plan.limit))))
        except (TypeError, ValueError):
            pass
        plan.source = "ollama+rules"
        return plan


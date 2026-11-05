from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from app.agent import EvidenceAgent
from app.db import Database


QUESTIONS = [
    "2024-yilda jami bitimlar summasi qancha?",
    "2025-yilda nechta bitim bor?",
    "2026-yil top-5 tovar",
    "2024-yilda eksport bitimlari summasi qancha?",
    "2025-yilda holatlar taqsimoti",
    "2023-yil o‘rtacha narx qancha?",
    "USD kursi 30.10.2026",
    "2021-yilda jami summa qancha?",
    "«MAVJUD EMAS» kompaniyasi profili",
    "Маржа по сделкам какая?",
    "В 2024 году сколько сделок?",
    "Топ-5 регионов за 2025 год",
    "Курс доллара на 30.10.2026",
    "Распределение статусов за 2026 год",
    "Сравни 2024 и 2025",
    "2022 yildan 2026 yilgacha barcha statistikani o‘zbek va rus tillarida ber",
    "Дайте полную статистику с 2022 по 2026 год",
    "2022–2026 yillar bo‘yicha top-10 region, status va eksport statistikasi",
]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Smoke/regression evaluation")
    parser.add_argument("--db", type=Path, default=Path("uzex.duckdb"))
    args = parser.parse_args()
    agent = EvidenceAgent(Database(args.db))
    durations = []
    safe = 0
    for question in QUESTIONS:
        started = time.perf_counter()
        result = agent.ask(question)
        elapsed = (time.perf_counter() - started) * 1000
        durations.append(elapsed)
        safe += int(result.safe)
        print(f"[{elapsed:8.1f} ms] {question}\n  {result.answer.replace(chr(10), ' | ')}")
    print(f"\nSavollar: {len(QUESTIONS)}; xavfsiz javoblar: {safe}/{len(QUESTIONS)}; o‘rtacha: {sum(durations)/len(durations):.1f} ms")


if __name__ == "__main__":
    main()


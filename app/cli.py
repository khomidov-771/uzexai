from __future__ import annotations

import argparse

from .agent import EvidenceAgent
from .config import Settings
from .db import Database
from .ollama import OllamaPlanner


def main() -> None:
    parser = argparse.ArgumentParser(description="UZEX AI agent — terminal rejimi")
    parser.add_argument("question", nargs="*", help="Savol; berilmasa interaktiv rejim")
    parser.add_argument("--db", default=None, help="DuckDB fayli")
    args = parser.parse_args()
    settings = Settings().resolved()
    db = Database(args.db or settings.db_path)
    planner = OllamaPlanner(settings.ollama_base_url, settings.ollama_model, settings.ollama_timeout_seconds) if settings.ollama_enabled else None
    agent = EvidenceAgent(db, ollama=planner, log_path=settings.root_dir / "logs" / "qa.jsonl")
    if args.question:
        print(agent.ask(" ".join(args.question)).answer)
        return
    print("UZEX AI Agent. Chiqish: exit yoki quit")
    while True:
        try:
            question = input("\nSavol> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if question.lower() in {"exit", "quit", "chiqish"}:
            break
        if question:
            print(agent.ask(question).answer)


if __name__ == "__main__":
    main()


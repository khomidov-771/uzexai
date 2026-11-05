from __future__ import annotations

from pathlib import Path
from typing import Any

from .agent import EvidenceAgent
from .config import Settings
from .db import Database
from .ollama import OllamaPlanner


def create_app(settings: Settings | None = None):
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel, Field
    except ImportError as exc:
        raise RuntimeError("FastAPI/Pydantic topilmagan. `pip install -r requirements.txt` ni ishga tushiring.") from exc

    cfg = (settings or Settings()).resolved()
    db = Database(cfg.db_path)
    planner = OllamaPlanner(cfg.ollama_base_url, cfg.ollama_model, cfg.ollama_timeout_seconds) if cfg.ollama_enabled else None
    agent = EvidenceAgent(db, ollama=planner, log_path=cfg.root_dir / "logs" / "qa.jsonl")
    app = FastAPI(title="UZEX AI Agent", version="1.0.0", description="Evidence-first UZEX analytics API")

    class AskRequest(BaseModel):
        question: str = Field(min_length=1, max_length=2000)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "database": str(cfg.db_path), "data_range": [agent.min_date, agent.max_date], "ollama": bool(planner)}

    @app.get("/stats")
    def stats() -> dict[str, Any]:
        return agent.db.table_stats()

    @app.post("/ask")
    def ask(body: AskRequest) -> dict[str, Any]:
        result = agent.ask(body.question)
        return {
            "answer": result.answer,
            "intent": result.intent,
            "language": result.language,
            "evidence": result.evidence,
            "safe": result.safe,
            "latency_ms": result.latency_ms,
        }

    @app.post("/explain")
    def explain(body: AskRequest) -> dict[str, Any]:
        result = agent.ask(body.question)
        return {"answer": result.answer, "sql": result.sql, "params": result.params, "evidence": result.evidence}

    return app


def main() -> None:
    import uvicorn

    uvicorn.run("app.api:create_app", factory=True, host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()


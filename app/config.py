from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _bool_env(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    root_dir: Path = ROOT_DIR
    data_dir: Path = Path(os.getenv("UZEX_DATA_DIR", str(ROOT_DIR / "uzex_spot_data")))
    db_path: Path = Path(os.getenv("UZEX_DB_PATH", str(ROOT_DIR / "uzex.duckdb")))
    ollama_enabled: bool = _bool_env("OLLAMA_ENABLED")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
    ollama_timeout_seconds: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "20"))
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

    def resolved(self) -> "Settings":
        return Settings(
            root_dir=self.root_dir,
            data_dir=self.data_dir.expanduser().resolve(),
            db_path=self.db_path.expanduser().resolve(),
            ollama_enabled=self.ollama_enabled,
            ollama_base_url=self.ollama_base_url.rstrip("/"),
            ollama_model=self.ollama_model,
            ollama_timeout_seconds=self.ollama_timeout_seconds,
            telegram_bot_token=self.telegram_bot_token,
        )


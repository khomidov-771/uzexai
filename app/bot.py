from __future__ import annotations

import asyncio

from .agent import EvidenceAgent
from .config import Settings
from .db import Database
from .ollama import OllamaPlanner


async def run() -> None:
    try:
        from aiogram import Bot, Dispatcher, F
        from aiogram.filters import CommandStart
        from aiogram.types import Message
    except ImportError as exc:
        raise RuntimeError("Telegram uchun `pip install -e '.[bot]'` ni ishga tushiring.") from exc
    cfg = Settings().resolved()
    if not cfg.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN .env faylida ko‘rsatilmagan.")
    db = Database(cfg.db_path)
    planner = OllamaPlanner(cfg.ollama_base_url, cfg.ollama_model, cfg.ollama_timeout_seconds) if cfg.ollama_enabled else None
    agent = EvidenceAgent(db, ollama=planner, log_path=cfg.root_dir / "logs" / "qa.jsonl")
    bot = Bot(cfg.telegram_bot_token)
    dispatcher = Dispatcher()

    @dispatcher.message(CommandStart())
    async def start(message: Message) -> None:
        await message.answer(
            "UZEX AI Agent\n\nSavol yuboring. Masalan:\n"
            "• 2025-yilda jami bitimlar summasi qancha?\n"
            "• 2024-yil top-5 tovar\n"
            "• 950000000 kompaniyasi profili\n"
            "• USD kursi 30.10.2026\n\n"
            "Agent barcha raqamlarni DuckDB hisobidan oladi va manbani ko‘rsatadi."
        )

    @dispatcher.message(F.text)
    async def question(message: Message) -> None:
        thinking = await message.answer("⏳ Tahlil qilinmoqda…")
        result = await asyncio.to_thread(agent.ask, message.text or "")
        await thinking.edit_text(result.answer[:4096])

    await dispatcher.start_polling(bot)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()


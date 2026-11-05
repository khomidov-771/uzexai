# UZEX AI Agent

UZEX spot dataseti uchun lokal, dalilga asoslangan Uzbek/Russian analytics agent.
Agent raqamlarni LLMdan olmaydi: barcha summa, son, hajm, narx, top va status statistikasi DuckDB SQL orqali hisoblanadi. Javobdagi raqamlar validator bilan tekshiriladi; natija bo‘lmasa taxmin qilinmaydi.

> Public GitHub repo’ga xom CSV fayllar joylanmaydi. `uzex_spot_data/` papkasini dataset bilan alohida, private volume sifatida qo‘ying.

## Tez ishga tushirish

PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/build_db.py --data-dir uzex_spot_data --db uzex.duckdb
python -m app.cli "2025-yilda jami bitimlar summasi qancha?"
```

GitHub’dan clone qilgandan keyin ham shu dataset papkasini lokal/VPS’da qo‘yib, `build_db.py` ni ishga tushiring. Docker Compose shu papkani read-only volume sifatida ulaydi.

Interaktiv CLI:

```powershell
python -m app.cli
```

Web API:

```powershell
uvicorn app.api:create_app --factory --host 127.0.0.1 --port 8000
```

`POST /ask` body: `{"question":"2024-yilda top-5 tovar qaysilar?"}`

`GET /stats` umumiy dataset statistikasini, `GET /health` holatni, `POST /explain` esa javob bilan birga parametrli SQL va filtrlarni qaytaradi.

## Qo‘llab-quvvatlanadigan savollar

- davr bo‘yicha jami summa, bitimlar soni, hajm;
- top mahsulot, kompaniya, region, broker va status;
- o‘rtacha/min/max narx;
- kompaniya profili, INN bo‘yicha qidiruv;
- kontrakt yoki oxirgi bitim;
- eksport summasi va bitim sanasidagi USD kursi bo‘yicha so‘mdagi ekvivalent;
- status taqsimoti, USD kursi va ikki yil taqqoslash;
- Uzbek lotin/kirill va ruscha savollar.

Default qoidalar: summa/hajm statistikasi annul qilingan bitimlarni chiqaradi, bitimlar soni esa barcha statuslarni sanaydi. Javobda davr, status filtri, valyuta va hisoblangan qatorlar ko‘rsatiladi.

## Optional Qwen/Ollama

Deterministik rejim asosiy va mustaqil ishlaydi. Faqat intentni tushunish qiyin bo‘lgan savollarda Qwen planner fallbackini yoqish mumkin:

```powershell
ollama pull qwen2.5:7b-instruct
Copy-Item .env.example .env
# .env ichida OLLAMA_ENABLED=true qiling
```

Ollama xom qatorlar yoki hisoblangan raqamlarni ko‘rmaydi, SQL bajarmaydi va javob yozmaydi. U faqat ruxsat berilgan intentlardan birini tanlashga yordam beradi. Ollama o‘chiq yoki timeout bo‘lsa, agent xavfsiz shablon rejimida ishlaydi.

## Telegram

`.env` ichiga `TELEGRAM_BOT_TOKEN` yozing, keyin:

```powershell
pip install -e ".[bot]"
python -m app.bot
```

## Test va baholash

```powershell
pytest
python scripts/eval.py --db uzex.duckdb
```

## Fayllar

- `scripts/build_db.py` — CSV → DuckDB ETL, normalizatsiya va ASOF USD kurs joini.
- `app/agent.py` — query planning, parametrli SQL, javob shablonlari va validator.
- `app/api.py` — FastAPI health/stats/ask/explain endpointlari.
- `app/cli.py` — lokal terminal agenti.
- `app/bot.py` — Telegram adapteri.
- `SOLUTION.md` — arxitektura, qabul qilingan farazlar va tekshiruv qoidalari.


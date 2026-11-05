FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml requirements.txt ./
COPY app ./app
COPY scripts ./scripts
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000
CMD ["sh", "-c", "python scripts/build_db.py --data-dir uzex_spot_data --db uzex.duckdb && uvicorn app.api:create_app --factory --host 0.0.0.0 --port 8000"]


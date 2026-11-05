from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


class DatabaseUnavailable(RuntimeError):
    pass


class Database:
    """Small read-only DuckDB gateway. All user values are bound parameters."""

    def __init__(self, path: str | Path):
        try:
            import duckdb
        except ImportError as exc:
            raise DatabaseUnavailable("DuckDB topilmagan. `pip install -r requirements.txt` ni ishga tushiring.") from exc
        self.path = Path(path).expanduser().resolve()
        if not self.path.exists():
            raise DatabaseUnavailable(f"Baza topilmadi: {self.path}. Avval `python scripts/build_db.py` ni ishga tushiring.")
        self.connection = duckdb.connect(str(self.path), read_only=True)
        self.connection.execute("SET enable_external_access=false")
        self.connection.execute("SET threads=4")

    def close(self) -> None:
        self.connection.close()

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        cursor = self.connection.execute(sql, list(params))
        names = [item[0] for item in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]

    def one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Iterable[Any] = ()) -> Any:
        row = self.one(sql, params)
        return next(iter(row.values())) if row else None

    def table_stats(self) -> dict[str, Any]:
        return self.one(
            """
            SELECT
              COUNT(*) AS deal_count,
              MIN(deal_date) AS min_date,
              MAX(deal_date) AS max_date,
              COUNT(DISTINCT seller_inn) + COUNT(DISTINCT buyer_inn) AS participant_mentions,
              COUNT(DISTINCT product) AS product_count,
              SUM(amount_uzs) AS total_amount_uzs,
              SUM(volume) AS total_volume
            FROM deals_enriched
            """
        ) or {}


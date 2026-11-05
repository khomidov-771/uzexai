from __future__ import annotations

import argparse
import sys
from pathlib import Path


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


def build(data_dir: Path, db_path: Path) -> None:
    try:
        import duckdb
    except ImportError as exc:
        raise SystemExit("DuckDB topilmadi. `pip install -r requirements.txt` ni ishga tushiring.") from exc

    data_dir = data_dir.resolve()
    db_path = db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    deals_glob = sql_path(data_dir / "deals_*.csv")
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute("PRAGMA threads=4")
        conn.execute("DROP VIEW IF EXISTS deals_enriched")
        conn.execute("DROP VIEW IF EXISTS contracts_full")
        conn.execute(
            f"""
            CREATE OR REPLACE TABLE deals_raw AS
            SELECT * FROM read_csv_auto('{deals_glob}', header=true, all_varchar=true,
              union_by_name=true, delim=',', quote='"', encoding='utf-8')
            """
        )
        conn.execute(
            f"""
            CREATE OR REPLACE TABLE participants AS
            SELECT
              trim("ИНН") AS inn,
              trim("Наименование") AS name,
              trim("Регион") AS region,
              trim("Вид деятельности") AS activity,
              trim("Роль") AS role,
              trim("Плательщик НДС") AS vat_payer
            FROM read_csv_auto('{sql_path(data_dir / 'participants.csv')}', header=true, all_varchar=true,
              delim=',', quote='"', encoding='utf-8')
            """
        )
        conn.execute(
            f"""
            CREATE OR REPLACE TABLE brokers AS
            SELECT
              trim("Код брокера") AS broker_code,
              trim("Наименование") AS name,
              trim("ИНН") AS inn,
              trim("Регион") AS region
            FROM read_csv_auto('{sql_path(data_dir / 'brokers.csv')}', header=true, all_varchar=true,
              delim=',', quote='"', encoding='utf-8')
            """
        )
        conn.execute(
            f"""
            CREATE OR REPLACE TABLE contracts AS
            SELECT
              TRY_CAST(NULLIF(trim("Номер контракта"), '') AS BIGINT) AS contract_id,
              trim("Наименование продукта") AS product,
              trim("Марка товара") AS brand,
              trim("Размер товара") AS product_size,
              trim("Сорт товара") AS product_grade,
              trim("Тип товара") AS product_type,
              trim("Класс товара") AS product_class,
              trim("Код ТН ВЭД") AS tnved_code,
              trim("Группа товара") AS product_group,
              trim("Категория товара") AS category,
              trim("Отрасль промышленности") AS industry,
              trim("Единица измерения") AS unit,
              TRY_CAST(NULLIF(trim("Лот"), '') AS DOUBLE) AS lot,
              trim("Валюта") AS currency,
              TRY_CAST(regexp_replace(NULLIF(trim("Базисная цена"), ''), '[^0-9.-]', '', 'g') AS DOUBLE) AS base_price,
              trim("Сумма залога") AS deposit,
              trim("Базис поставки") AS delivery_basis,
              trim("Регион") AS region,
              trim("Адрес склада") AS warehouse_address,
              trim("Тип торгов") AS trade_type,
              trim("Тип контракта") AS contract_type,
              trim("Форма контракта") AS contract_form,
              trim("Срок оплаты") AS payment_term,
              trim("Срок поставки") AS delivery_term,
              trim("Упаковка") AS packaging,
              trim("ИНН продавца") AS seller_inn,
              TRY_STRPTIME(NULLIF(trim("Дата регистрации"), ''), '%d.%m.%Y')::DATE AS registered_date,
              TRY_STRPTIME(NULLIF(trim("Действует до"), ''), '%d.%m.%Y')::DATE AS valid_until
            FROM read_csv_auto('{sql_path(data_dir / 'contracts.csv')}', header=true, all_varchar=true,
              delim=',', quote='"', encoding='utf-8')
            """
        )
        conn.execute(
            f"""
            CREATE OR REPLACE TABLE usd_rates AS
            SELECT
              TRY_STRPTIME(NULLIF(trim("Дата"), ''), '%d.%m.%Y')::DATE AS rate_date,
              TRY_CAST(regexp_replace(NULLIF(trim("Курс"), ''), '[^0-9.-]', '', 'g') AS DOUBLE) AS usd_rate
            FROM read_csv_auto('{sql_path(data_dir / 'usd_rates.csv')}', header=true, all_varchar=true,
              delim=',', quote='"', encoding='utf-8')
            WHERE NULLIF(trim("Дата"), '') IS NOT NULL
            """
        )
        conn.execute(
            """
            CREATE OR REPLACE TABLE deals AS
            SELECT
              TRY_CAST(NULLIF(trim("Номер сделки"), '') AS BIGINT) AS deal_id,
              TRY_STRPTIME(NULLIF(trim("Дата сделки"), ''), '%d.%m.%Y')::DATE AS deal_date,
              trim("Время сделки") AS deal_time,
              trim("Тип торгов") AS trade_type,
              TRY_CAST(regexp_replace(NULLIF(trim("Количество"), ''), '[^0-9.-]', '', 'g') AS DOUBLE) AS quantity,
              TRY_CAST(regexp_replace(NULLIF(trim("Сумма сделки"), ''), '[^0-9.-]', '', 'g') AS DOUBLE) AS amount,
              TRY_CAST(regexp_replace(NULLIF(trim("Стартовая цена"), ''), '[^0-9.-]', '', 'g') AS DOUBLE) AS start_price,
              TRY_CAST(NULLIF(trim("Номер контракта"), '') AS BIGINT) AS contract_id,
              trim("Наименование товара") AS product,
              TRY_CAST(regexp_replace(NULLIF(trim("Лот"), ''), '[^0-9.-]', '', 'g') AS DOUBLE) AS lot,
              trim("Единица измерения") AS unit,
              trim("Регион") AS region,
              trim("Тип контракта") AS contract_type,
              trim("Форма контракта") AS form,
              trim("Состояние сделки") AS status,
              trim("ИНН продавца") AS seller_inn,
              trim("ИНН покупателя") AS buyer_inn,
              trim("Брокер продавца") AS seller_broker,
              trim("Брокер покупателя") AS buyer_broker,
              TRY_STRPTIME(NULLIF(trim("Дата оплаты"), ''), '%d.%m.%Y')::DATE AS payment_date,
              TRY_STRPTIME(NULLIF(trim("Дата поставки"), ''), '%d.%m.%Y')::DATE AS delivery_date,
              TRY_CAST(regexp_replace(NULLIF(trim("Поставлено"), ''), '[^0-9.-]', '', 'g') AS DOUBLE) AS delivered
            FROM deals_raw
            """
        )
        conn.execute(
            """
            CREATE OR REPLACE VIEW contracts_full AS
            SELECT c.*, p.name AS seller_name
            FROM contracts c
            LEFT JOIN participants p ON p.inn = c.seller_inn
            """
        )
        conn.execute(
            """
            CREATE OR REPLACE VIEW deals_enriched AS
            SELECT
              d.*,
              COALESCE(c.product, d.product) AS contract_product,
              c.currency AS contract_currency,
              c.base_price,
              c.region AS contract_region,
              c.product_group,
              c.category,
              c.industry,
              c.tnved_code,
              c.packaging,
              c.delivery_basis,
              sp.name AS seller_name,
              sp.region AS seller_region,
              sp.activity AS seller_activity,
              bp.name AS buyer_name,
              bp.region AS buyer_region,
              bp.activity AS buyer_activity,
              sb.name AS seller_broker_name,
              bb.name AS buyer_broker_name,
              r.usd_rate,
              d.quantity * COALESCE(NULLIF(d.lot, 0), NULLIF(c.lot, 0), 1) AS volume,
              CASE WHEN d.quantity * COALESCE(NULLIF(d.lot, 0), NULLIF(c.lot, 0), 1) = 0
                THEN NULL
                ELSE d.amount / (d.quantity * COALESCE(NULLIF(d.lot, 0), NULLIF(c.lot, 0), 1))
              END AS unit_price,
              CASE
                WHEN lower(COALESCE(c.currency, '')) LIKE '%доллар%'
                  OR d.trade_type = 'Экспортный'
                THEN d.amount * r.usd_rate
                ELSE d.amount
              END AS amount_uzs
            FROM deals d
            LEFT JOIN contracts c ON c.contract_id = d.contract_id
            LEFT JOIN participants sp ON sp.inn = d.seller_inn
            LEFT JOIN participants bp ON bp.inn = d.buyer_inn
            LEFT JOIN brokers sb ON sb.broker_code = d.seller_broker
            LEFT JOIN brokers bb ON bb.broker_code = d.buyer_broker
            ASOF LEFT JOIN usd_rates r ON d.deal_date >= r.rate_date
            """
        )
        conn.execute("CHECKPOINT")
        stats = conn.execute(
            "SELECT COUNT(*) AS deals, MIN(deal_date), MAX(deal_date) FROM deals"
        ).fetchone()
        print(f"Baza tayyor: {db_path}")
        print(f"Bitimlar: {stats[0]:,}; davr: {stats[1]} — {stats[2]}")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="UZEX CSV fayllaridan DuckDB baza yaratish")
    parser.add_argument("--data-dir", type=Path, default=Path("uzex_spot_data"))
    parser.add_argument("--db", type=Path, default=Path("uzex.duckdb"))
    args = parser.parse_args()
    build(args.data_dir, args.db)


if __name__ == "__main__":
    main()


"""
Run q12 heavy SQL locally and store results in lightweight DB tables.
Run once via: python -m scripts.materialize_q12
Production q12 then reads from these tables (instant).
To write through a fly proxy tunnel to production, set ALLOW_PROD_DB=1.
"""
import os
from sqlalchemy import create_engine, text

from scripts import prod_guard

prod_guard.check(os.environ["DATABASE_URL"])
engine = create_engine(os.environ["DATABASE_URL"])

_SQL_SUMMARY = """
WITH forecast AS (
    SELECT sku, store_id, avg_weekly_units AS forecast_units
    FROM public_marts.fct_distribution
    WHERE is_active = true AND avg_weekly_units > 0
),
errors AS (
    SELECT
        sd.sku,
        ABS(sd.units_sold - f.forecast_units) / NULLIF(sd.units_sold::numeric, 0) AS abs_pct_error
    FROM public_marts.fct_scan_data sd
    JOIN forecast f ON f.sku = sd.sku AND f.store_id = sd.store_id
    WHERE sd.units_sold > 0
)
SELECT
    ROUND(AVG(abs_pct_error)::numeric * 100, 1) AS mape_pct,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY abs_pct_error)::numeric * 100, 1) AS median_ape_pct,
    COUNT(DISTINCT sku) AS sku_count,
    COUNT(*) AS data_points
FROM errors
"""

_SQL_BY_SKU = """
WITH forecast AS (
    SELECT sku, store_id, avg_weekly_units AS forecast_units
    FROM public_marts.fct_distribution
    WHERE is_active = true AND avg_weekly_units > 0
),
errors AS (
    SELECT
        sd.sku,
        f.forecast_units,
        ABS(sd.units_sold - f.forecast_units) / NULLIF(sd.units_sold::numeric, 0) AS abs_pct_error
    FROM public_marts.fct_scan_data sd
    JOIN forecast f ON f.sku = sd.sku AND f.store_id = sd.store_id
    WHERE sd.units_sold > 0
)
SELECT
    e.sku,
    dp.product_name,
    ROUND(AVG(e.abs_pct_error)::numeric * 100, 1) AS mape_pct,
    ROUND(AVG(e.forecast_units)::numeric, 1) AS avg_forecast_units
FROM errors e
JOIN public_marts.dim_products dp ON dp.sku = e.sku
GROUP BY e.sku, dp.product_name
ORDER BY mape_pct DESC
LIMIT 10
"""

print("Connecting to DB...")
with engine.connect() as conn:
    conn = conn.execution_options(isolation_level="AUTOCOMMIT")
    conn.execute(text("SET statement_timeout = '0'"))
    conn.execute(text("SET work_mem = '128MB'"))

    print("Running heavy q12 summary query (may take 60-120s)...")
    summary = conn.execute(text(_SQL_SUMMARY)).fetchone()
    print(f"Summary: mape={summary[0]}%, median={summary[1]}%, skus={summary[2]}, rows={summary[3]}")

    print("Running by-SKU query...")
    by_sku = conn.execute(text(_SQL_BY_SKU)).fetchall()
    print(f"By-SKU: {len(by_sku)} rows")

    print("Creating precomputed tables...")
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS public_marts.q12_summary (
            mape_pct NUMERIC,
            median_ape_pct NUMERIC,
            sku_count INT,
            data_points BIGINT
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS public_marts.q12_by_sku (
            sku TEXT,
            product_name TEXT,
            mape_pct NUMERIC,
            avg_forecast_units NUMERIC
        )
    """))

    conn.execute(text("TRUNCATE public_marts.q12_summary"))
    conn.execute(text("TRUNCATE public_marts.q12_by_sku"))

    conn.execute(text("""
        INSERT INTO public_marts.q12_summary VALUES (:mape, :median, :skus, :rows)
    """), {"mape": summary[0], "median": summary[1], "skus": summary[2], "rows": summary[3]})

    for row in by_sku:
        conn.execute(text("""
            INSERT INTO public_marts.q12_by_sku VALUES (:sku, :product_name, :mape, :forecast)
        """), {"sku": row[0], "product_name": row[1], "mape": row[2], "forecast": row[3]})

    print("Done. Tables q12_summary and q12_by_sku populated.")

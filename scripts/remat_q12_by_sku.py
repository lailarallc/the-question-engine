"""Re-run only the by-SKU materialization (summary already populated)."""
import os
from sqlalchemy import create_engine, text

from scripts import prod_guard

prod_guard.check(os.environ["DATABASE_URL"])
engine = create_engine(os.environ["DATABASE_URL"])

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

print("Running store-week by-SKU MAPE query (may take 60-120s)...")
with engine.connect() as conn:
    conn = conn.execution_options(isolation_level="AUTOCOMMIT")
    conn.execute(text("SET statement_timeout = '0'"))
    conn.execute(text("SET work_mem = '128MB'"))

    rows = conn.execute(text(_SQL_BY_SKU)).fetchall()
    print(f"Got {len(rows)} SKU rows")
    for r in rows[:3]:
        print(f"  {r[1]}: {r[2]}%")

    conn.execute(text("TRUNCATE public_marts.q12_by_sku"))
    for row in rows:
        conn.execute(text(
            "INSERT INTO public_marts.q12_by_sku VALUES (:sku, :product_name, :mape, :forecast)"
        ), {"sku": row[0], "product_name": row[1], "mape": row[2], "forecast": row[3]})

    print("Done. q12_by_sku repopulated with store-week level MAPE.")

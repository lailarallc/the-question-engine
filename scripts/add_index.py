"""Add index to fct_scan_data for q12 query performance."""
import os
import time
from sqlalchemy import create_engine, text

from scripts import prod_guard

prod_guard.check(os.environ["DATABASE_URL"])
engine = create_engine(os.environ["DATABASE_URL"])
with engine.connect() as conn:
    conn = conn.execution_options(isolation_level="AUTOCOMMIT")
    print("Creating index on fct_scan_data(sku, store_id) CONCURRENTLY...")
    t0 = time.time()
    conn.execute(text(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_scan_sku_store "
        "ON public_marts.fct_scan_data(sku, store_id)"
    ))
    print(f"Done in {time.time()-t0:.1f}s")

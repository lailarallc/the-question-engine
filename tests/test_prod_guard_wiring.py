"""The prod guard sits in front of every script that writes to Postgres.

materialize_q12, remat_q12_by_sku and add_index create, truncate, insert and
index at DATABASE_URL -- localhost:5432 is a `fly proxy` tunnel to production
when one is open. The scripts connect at import, so these tests run each one
with a faked flyctl listener and assert create_engine is never reached.
"""

import runpy

import pytest
import sqlalchemy

from scripts import prod_guard


@pytest.mark.parametrize("script", ["materialize_q12", "remat_q12_by_sku", "add_index"])
def test_write_script_refuses_fly_tunnel(script, monkeypatch):
    monkeypatch.delenv("ALLOW_PROD_DB", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u@localhost:5432/db")
    monkeypatch.setattr(prod_guard, "_listener", lambda port: "flyctl")
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *a, **kw: pytest.fail("create_engine ran"))
    with pytest.raises(prod_guard.ProdDatabaseError):
        runpy.run_module(f"scripts.{script}", run_name="__main__")

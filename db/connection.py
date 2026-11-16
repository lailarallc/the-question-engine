import os
from typing import Any

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

from engine.labels import label_rows

load_dotenv()

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError(
                "DATABASE_URL is not set. Add it to your environment or .env file, "
                "e.g. DATABASE_URL=postgresql://user:pass@localhost:5432/dbname"
            )
        # `fly pg attach` (and Heroku-style configs) emit the legacy "postgres://"
        # scheme, which SQLAlchemy 2.x refuses to load ("Can't load plugin:
        # sqlalchemy.dialects:postgres"). Normalize to the canonical dialect.
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        _engine = create_engine(url)
    return _engine


def query(sql: str, params: dict | None = None) -> list[dict[str, Any]]:
    """Execute a read-only query and return rows as dicts."""
    with _get_engine().connect() as conn:
        result = conn.execute(text(sql), params or {})
        cols = result.keys()
        # Partner names leave the database as role labels (engine/labels.py).
        return label_rows([dict(zip(cols, row)) for row in result.fetchall()])

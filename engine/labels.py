"""Public display labels for Cinderhaven's trade partners.

The dataset keeps the real partner names. Every verdict, key number and chart
this engine returns shows the role label instead, because each one sits beside
a Cinderhaven figure. The map is vendored from lailara-website
(reference/retailer_display_labels.json, decided 2026-11-05).
"""

from __future__ import annotations

import json
from pathlib import Path

_MAP_PATH = Path(__file__).resolve().parent.parent / "reference" / "retailer_display_labels.json"


def _load() -> dict[str, str]:
    raw = json.loads(_MAP_PATH.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for group in ("retailers", "distributors", "other_partners"):
        for key, entry in raw.get(group, {}).items():
            if key.startswith("_"):
                continue
            label = entry["label"]
            for name in [entry["name"], *entry.get("aliases", [])]:
                out[name.lower()] = label
    return out


_LABELS = _load()

# Row keys that carry a partner name in query results.
NAME_KEYS = ("retailer_name", "retailer", "distributor_name", "distributor")


def public_name(name: object) -> object:
    """Role label for a partner name, first letter capitalised. Others pass through."""
    if not isinstance(name, str):
        return name
    label = _LABELS.get(name.strip().lower())
    if label is None:
        return name
    return label[0].upper() + label[1:]


def label_rows(rows: list[dict]) -> list[dict]:
    """Swap partner names for role labels in every query row."""
    for row in rows:
        for key in NAME_KEYS:
            if key in row:
                row[key] = public_name(row[key])
    return rows

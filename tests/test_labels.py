"""Partner names leave the engine as role labels, never as real names."""

import re
from pathlib import Path
from unittest.mock import patch

from engine.labels import label_rows, public_name

ROOT = Path(__file__).resolve().parent.parent
REAL = re.compile(r"Walmart|Costco|Kroger|Whole Foods|Sprouts|UNFI|KeHE|DPI")


def test_real_partner_names_become_role_labels():
    assert public_name("Walmart") == "National mass retailer"
    assert public_name("KeHE") == "Distributor B"
    assert public_name("Regional Group") == "Regional Group"
    assert public_name(None) is None


def test_every_name_key_is_relabelled_in_query_rows():
    rows = label_rows([
        {"retailer_name": "Costco", "amount": 5},
        {"retailer": "Whole Foods", "amount": 6},
        {"distributor_name": "UNFI", "amount": 7},
    ])
    assert not REAL.search(str(rows))


def test_query_layer_applies_the_labels():
    src = (ROOT / "db" / "connection.py").read_text(encoding="utf-8")
    assert "label_rows(" in src


def test_otif_verdict_names_no_partner_beside_a_cinderhaven_figure():
    from engine.questions.q13_otif_exposure import OtifExposureQuestion

    def fake_query(sql, params=None):
        if "cases_ordered" in sql:
            return [{"cases_ordered": 100.0, "cases_ordered_dated": 100.0, "cases_on_time": 96.0,
                     "cases_delivered": 98.0, "undated_lines": 0,
                     "undated_first_ship": None, "undated_last_ship": None}]
        if "GROUP BY dr.retailer_name" in sql:
            return [{"retailer_name": public_name("Walmart"), "asn_late_rate": 0.097,
                     "late_asn": 327, "total_shipments": 3371, "on_time_rate": 0.9}]
        return [{"window_year": 2025, "total_shipments": 15530, "late_asn_count": 1344,
                 "asn_late_rate": 0.0865, "walmart_late_asn": 327}]

    with patch("engine.questions.q13_otif_exposure.query", side_effect=fake_query):
        result = OtifExposureQuestion().run()

    shown = " ".join([result.verdict, result.verdict_detail or ""]
                     + [f"{k.label} {k.value} {k.context}" for k in result.key_numbers])
    assert not REAL.search(shown), shown
    assert not REAL.search(result.rule_explanation), result.rule_explanation

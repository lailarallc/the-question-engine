"""
Q04: Where is my trade spend going?

Uses DISTRESSED scenario — reads the full deduction universe including disputed/expired,
matching what the Trade Spend Data Diagnostic piece shows.

Rule: if unplanned deductions (compliance, shortage, damage — not promo) exceed
UNPLANNED_THRESHOLD of total deductions, verdict is "you have a leakage problem."

Thresholds calibrated from Trade Spend Diagnostic piece.
"""
import yaml
from pathlib import Path

from engine.base import BaseQuestion
from engine.registry import registry
from api.models.schemas import VerdictResponse, QuestionMeta, KeyNumber, ChartData
from db.connection import query

_CFG = yaml.safe_load(
    (Path(__file__).parent.parent.parent / "config" / "thresholds.yaml").read_text()
)["q04"]

# Planned = promotional deductions (agreed-in-advance trade spend)
# Unplanned = compliance, shortage, damage, post-audit — money taken without prior agreement
_UNPLANNED_TYPES = ("compliance", "shortage", "damage", "post_audit", "audit")

_SQL_DEDUCTIONS = """
SELECT
    LOWER(deduction_type)                        AS deduction_type,
    SUM(deduction_amount)                        AS gross_amount,
    SUM(net_deduction_amount)                    AS net_amount,
    COUNT(*)                                     AS count,
    ROUND(AVG(typical_recovery_rate)::numeric, 4) AS avg_recovery_rate
FROM public_marts.fct_retailer_deductions
GROUP BY LOWER(deduction_type)
ORDER BY gross_amount DESC
"""

# No filter on funding_mechanism: no row has the value 'manufacturer'. The actual
# values (off_invoice, MCB, scan_based, billback) are all manufacturer-funded, same
# fix as q02 (FAILURES.md 2026-06-10). Total = canonical trade.promotional_spend.trailing_36m.
_SQL_PROMO = """
SELECT
    SUM(promo_cost)                AS total_promo_cost,
    SUM(promo_cost)                AS mfr_funded,
    COUNT(*)                       AS promo_count
FROM public_marts.fct_promotions
"""


class TradeSpendQuestion(BaseQuestion):
    def meta(self) -> QuestionMeta:
        return QuestionMeta(
            id="q04",
            question="Where is my trade spend going?",
            short_label="Trade spend going where?",
            source_piece="Trade Spend Data Diagnostic",
            go_deeper_link="https://lailarallc.com/trade-spend-diagnostic",
            scenario="distressed",
        )

    def run(self) -> VerdictResponse:
        ded_rows = query(_SQL_DEDUCTIONS)
        promo_row = query(_SQL_PROMO)[0]

        total_deductions = sum(float(r["gross_amount"]) for r in ded_rows)
        unplanned_amount = sum(
            float(r["gross_amount"]) for r in ded_rows
            if any(t in r["deduction_type"] for t in _UNPLANNED_TYPES)
        )
        planned_amount = total_deductions - unplanned_amount
        mfr_promo = float(promo_row["mfr_funded"] or 0)
        total_trade = total_deductions + mfr_promo

        unplanned_rate = unplanned_amount / total_deductions if total_deductions > 0 else 0
        cfg = _CFG

        if unplanned_rate > cfg["unplanned_deduction_threshold"]:
            verdict = (
                f"{unplanned_rate:.0%} of your deductions are unplanned — "
                f"compliance fines, shortages, and post-audit clawbacks that were never agreed to. "
                f"Industry expectation is under {cfg['unplanned_deduction_threshold']:.0%}. "
                f"That gap represents ${unplanned_amount - total_deductions * cfg['unplanned_deduction_threshold']:,.0f} "
                f"in recoverable or preventable spend."
            )
            verdict_detail = "leakage problem"
        else:
            verdict = (
                f"Trade spend looks controlled: {unplanned_rate:.0%} of deductions are unplanned, "
                f"within the {cfg['unplanned_deduction_threshold']:.0%} ceiling. "
                f"Total manufacturer promo investment: ${mfr_promo:,.0f}. "
                f"No structural leakage detected."
            )
            verdict_detail = "within range"

        chart_data = ChartData(
            type="bar",
            title="Gross deductions by type",
            data=[
                {
                    "type": r["deduction_type"].replace("_", " ").title(),
                    "gross_amount": float(r["gross_amount"]),
                    "net_amount": float(r["net_amount"]),
                }
                for r in ded_rows[:10]
            ],
            x_key="type",
            y_key="gross_amount",
            unit="dollars",
        )

        return VerdictResponse(
            question_id="q04",
            question=self.meta().question,
            verdict=verdict,
            verdict_detail=verdict_detail,
            key_numbers=[
                KeyNumber(label="Total deductions", value=f"${total_deductions:,.0f}"),
                KeyNumber(
                    label="Unplanned share",
                    value=f"{unplanned_rate:.0%}",
                    context="compliance, shortage, damage",
                ),
                KeyNumber(label="Manufacturer promo spend", value=f"${mfr_promo:,.0f}"),
            ],
            chart=chart_data,
            rule_explanation=(
                f"Unplanned = compliance + shortage + damage + post-audit deduction types. "
                f"Fires when unplanned share > {cfg['unplanned_deduction_threshold']:.0%} of total deductions. "
                f"Uses distressed scenario — full deduction universe including expired and disputed. "
                f"Thresholds from Trade Spend Diagnostic."
            ),
            go_deeper_link=self.meta().go_deeper_link,
            go_deeper_label=self.meta().source_piece,
            scenario=self.meta().scenario,
            source_piece=self.meta().source_piece,
        )


registry.register(TradeSpendQuestion())

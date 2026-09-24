"""
Q15: Why is cash tight when sales are up?

Reads fct_retailer_payments (remittance data) to quantify the two forces
that create a cash lag even when revenue is growing:
  1. Deduction drag — the silent haircut: 12–14% of every invoiced dollar
     disappears as deductions before cash arrives.
  2. DSO (Days Sales Outstanding) — the timing gap: cash arrives ~26 days
     after the PO (canonical workingcapital.dso_days).

Rule: fires when avg deduction rate > DEDUCTION_DRAG_WARNING OR
average DSO > DSO_WARNING. Both conditions together = "cash trap."

Routes to: contract-to-cash lifecycle analysis.
"""
import yaml
from pathlib import Path

from engine.base import BaseQuestion, NoDataError
from engine.registry import registry
from api.models.schemas import VerdictResponse, QuestionMeta, KeyNumber, ChartData
from db.connection import query

_CFG = yaml.safe_load(
    (Path(__file__).parent.parent.parent / "config" / "thresholds.yaml").read_text()
)["q15"]

# annual_gross / annual_year: the last full calendar year of remittances, so
# working capital = one year of gross / 365 × DSO (matches canonical
# revenue.gross_payments_retailer.trailing_12m). q13 uses the same year.
_SQL_SUMMARY = """
WITH yr AS (
    SELECT (EXTRACT(YEAR FROM MAX(received_date) + 1) - 1)::int AS y
    FROM public_marts.fct_retailer_payments
)
SELECT
    SUM(gross_amount)                                                           AS total_gross,
    SUM(net_amount)                                                             AS total_net,
    SUM(total_deductions)                                                       AS total_deductions,
    ROUND(AVG(total_deductions / NULLIF(gross_amount, 0))::numeric * 100, 2)   AS avg_deduction_rate,
    COUNT(*)                                                                    AS payment_count,
    ROUND(AVG(gross_amount)::numeric, 0)                                        AS avg_remittance,
    SUM(gross_amount) FILTER (WHERE EXTRACT(YEAR FROM received_date) = (SELECT y FROM yr))
                                                                                AS annual_gross,
    (SELECT y FROM yr)                                                          AS annual_year
FROM public_marts.fct_retailer_payments
"""

# DSO uses the canonical method (canonical_gather.sql, workingcapital.dso_days):
# order-value-weighted (received_date − po_date), each order matched to
# remittances received 25–55 days after the start of its PO month.
_SQL_DSO = """
SELECT
    ROUND(SUM(o.total_value * (r.received_date - o.po_date))
          / NULLIF(SUM(o.total_value), 0), 2) AS dso_days
FROM public_marts.fct_retailer_orders o
JOIN public_marts.fct_retailer_payments r
    ON r.retailer_id = o.retailer_id
    AND r.received_date BETWEEN date_trunc('month', o.po_date)::date + 25
                            AND date_trunc('month', o.po_date)::date + 55
"""

_SQL_BY_RETAILER = """
-- Payments and DSO are computed in separate CTEs to avoid fanout.
-- DSO per retailer uses the same canonical method as _SQL_DSO.
WITH payment_agg AS (
    SELECT
        p.retailer_id,
        COUNT(p.remittance_id)                                                        AS payment_count,
        ROUND(AVG(p.total_deductions / NULLIF(p.gross_amount, 0))::numeric * 100, 1) AS deduction_pct,
        SUM(p.gross_amount)                                                           AS total_gross,
        SUM(p.total_deductions)                                                       AS total_deductions
    FROM public_marts.fct_retailer_payments p
    GROUP BY p.retailer_id
),
dso_agg AS (
    SELECT
        o.retailer_id,
        ROUND(SUM(o.total_value * (r.received_date - o.po_date))
              / NULLIF(SUM(o.total_value), 0), 1) AS dso_days
    FROM public_marts.fct_retailer_orders o
    JOIN public_marts.fct_retailer_payments r
        ON r.retailer_id = o.retailer_id
        AND r.received_date BETWEEN date_trunc('month', o.po_date)::date + 25
                                AND date_trunc('month', o.po_date)::date + 55
    GROUP BY o.retailer_id
)
SELECT
    dr.retailer_name,
    pa.payment_count,
    pa.deduction_pct,
    da.dso_days,
    pa.total_gross,
    pa.total_deductions
FROM payment_agg pa
JOIN dso_agg da ON da.retailer_id = pa.retailer_id
JOIN public_marts.dim_retailers dr ON dr.retailer_id = pa.retailer_id
ORDER BY pa.deduction_pct DESC
"""


class CashConversionQuestion(BaseQuestion):
    def meta(self) -> QuestionMeta:
        return QuestionMeta(
            id="q15",
            question="Why is cash tight when sales are up?",
            short_label="Why is cash tight?",
            source_piece="Contract-to-Cash Lifecycle",
            go_deeper_link="https://lailarallc.com/contract-to-cash",
            scenario="baseline",
        )

    def run(self) -> VerdictResponse:
        summary_rows = query(_SQL_SUMMARY)
        dso_rows = query(_SQL_DSO)
        by_retailer = query(_SQL_BY_RETAILER)
        if not summary_rows or not by_retailer:
            raise NoDataError("q15: no remittance data returned")
        summary = summary_rows[0]

        total_gross = float(summary["total_gross"] or 0)
        total_net = float(summary["total_net"] or 0)
        total_deductions = float(summary["total_deductions"] or 0)
        avg_deduction_rate = float(summary["avg_deduction_rate"] or 0)
        payment_count = int(summary["payment_count"] or 0)
        avg_remittance = float(summary["avg_remittance"] or 0)
        annual_gross = float(summary["annual_gross"] or 0)
        annual_year = int(summary["annual_year"])
        cfg = _CFG

        avg_dso = float(dso_rows[0]["dso_days"] or 0) if dso_rows else 0

        worst_deduction_retailer = by_retailer[0] if by_retailer else None
        deduction_drag_fires = avg_deduction_rate / 100 > cfg["deduction_drag_warning"]
        dso_fires = avg_dso > cfg["dso_warning"]

        # One year of gross (last full calendar year), not the whole multi-year history.
        working_capital_tied = (annual_gross / 365) * avg_dso if annual_gross > 0 else 0

        if deduction_drag_fires and dso_fires:
            verdict = (
                f"Cash is tight for two compounding reasons. "
                f"First, {avg_deduction_rate:.1f}% of every remittance is deducted before it arrives — "
                f"${total_deductions:,.0f} gone out of ${total_gross:,.0f} invoiced. "
                f"Second, cash takes {avg_dso:.0f} days to arrive after delivery "
                f"(above the {cfg['dso_warning']}-day warning threshold), "
                f"locking up ~${working_capital_tied:,.0f} in outstanding receivables at any moment. "
                f"Worst deduction account: {worst_deduction_retailer['retailer_name']} "
                f"at {float(worst_deduction_retailer['deduction_pct']):.1f}%."
            )
            verdict_detail = f"{avg_deduction_rate:.1f}% deduction drag + {avg_dso:.0f}-day DSO"
        elif deduction_drag_fires:
            verdict = (
                f"Deduction drag is the culprit: {avg_deduction_rate:.1f}% of every invoiced dollar "
                f"disappears as deductions before cash arrives — "
                f"${total_deductions:,.0f} deducted across {payment_count} remittances. "
                f"DSO is {avg_dso:.0f} days — within range. "
                f"Worst account: {worst_deduction_retailer['retailer_name']} "
                f"at {float(worst_deduction_retailer['deduction_pct']):.1f}% deduction rate."
            )
            verdict_detail = f"{avg_deduction_rate:.1f}% deduction drag"
        elif dso_fires:
            verdict = (
                f"Cash timing is the gap: {avg_dso:.0f}-day average DSO means "
                f"revenue shipped today doesn't arrive as cash for {avg_dso:.0f} days. "
                f"At current revenue rate, ~${working_capital_tied:,.0f} is perpetually outstanding. "
                f"Deduction rate ({avg_deduction_rate:.1f}%) is within the {cfg['deduction_drag_warning']:.0%} threshold."
            )
            verdict_detail = f"{avg_dso:.0f}-day DSO"
        else:
            verdict = (
                f"Cash conversion is healthy: {avg_deduction_rate:.1f}% average deduction rate "
                f"(below {cfg['deduction_drag_warning']:.0%} threshold), "
                f"{avg_dso:.0f}-day average DSO (below {cfg['dso_warning']}-day warning). "
                f"${total_deductions:,.0f} in deductions across ${total_gross:,.0f} invoiced. "
                f"The gap between sales and cash is expected, not a structural problem."
            )
            verdict_detail = "healthy cash conversion"

        chart_data = ChartData(
            type="bar",
            title="Deduction rate by retailer",
            data=[
                {
                    "retailer": r["retailer_name"],
                    "deduction_pct": float(r["deduction_pct"]),
                    "dso_days": float(r["dso_days"]),
                    "total_deductions": float(r["total_deductions"]),
                }
                for r in by_retailer
            ],
            x_key="retailer",
            y_key="deduction_pct",
            unit="percent",
        )

        return VerdictResponse(
            question_id="q15",
            question=self.meta().question,
            verdict=verdict,
            verdict_detail=verdict_detail,
            key_numbers=[
                KeyNumber(
                    label="Avg deduction rate",
                    value=f"{avg_deduction_rate:.1f}%",
                    context=f"${total_deductions:,.0f} of ${total_gross:,.0f} invoiced",
                ),
                KeyNumber(
                    label="Avg DSO",
                    value=f"{avg_dso:.0f} days",
                    context=f"warning at {cfg['dso_warning']} days",
                ),
                KeyNumber(
                    label="Working capital in transit",
                    value=f"${working_capital_tied:,.0f}",
                    context=f"{annual_year} gross ÷ 365 × avg DSO",
                ),
            ],
            chart=chart_data,
            rule_explanation=(
                f"Deduction drag = avg(total_deductions / gross_amount) from fct_retailer_payments. "
                f"DSO = order-value-weighted days from PO date to remittance, each order matched to "
                f"remittances received 25–55 days after the start of its PO month (canonical method). "
                f"Working capital = {annual_year} gross remittances ÷ 365 × DSO. "
                f"Fires when deduction rate > {cfg['deduction_drag_warning']:.0%} OR DSO > {cfg['dso_warning']} days. "
                f"Thresholds from Contract-to-Cash Lifecycle."
            ),
            go_deeper_link=self.meta().go_deeper_link,
            go_deeper_label=self.meta().source_piece,
            scenario=self.meta().scenario,
            source_piece=self.meta().source_piece,
        )


registry.register(CashConversionQuestion())

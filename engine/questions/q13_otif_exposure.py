"""
Q13: Am I about to get hit with OTIF penalties I can't see?

Reads fct_retailer_shipments for ASN compliance and on-time delivery over one
window: the last full calendar year, the same year q15 uses for working capital.

Rule: if asn_late_rate > ASN_LATE_RATE_THRESHOLD, fires with
exposure = Walmart late-ASN count × PENALTY_PER_ASN_LATE.

The $25/PO fee is Walmart's SQEP Phase 1 ASN defect fee, so only Walmart late
ASNs are priced. Other retailers' ASN fees are unknown and excluded (the page
says so). Walmart OTIF is scored by case, the way Walmart scores it (anchor
A5.16): on-time = cases delivered by MABD / cases ordered, against the 90%
prepaid target; in-full = whole cases delivered / cases ordered, against 95%.
Lines with no delivery date yet are left out of on-time. The 3% OTIF charge on
late or short cases is not dollarized here.

Routes to: OTIF Blind Spot.
"""
import yaml
from pathlib import Path

from engine.base import BaseQuestion
from engine.registry import registry
from api.models.schemas import VerdictResponse, QuestionMeta, KeyNumber, ChartData
from db.connection import query

_CFG = yaml.safe_load(
    (Path(__file__).parent.parent.parent / "config" / "thresholds.yaml").read_text()
)["q13"]

# Window = last full calendar year of remittances, the same year q15 uses.
_YEAR_CTE = """
WITH yr AS (
    SELECT (EXTRACT(YEAR FROM MAX(received_date) + 1) - 1)::int AS y
    FROM public_marts.fct_retailer_payments
)
"""

_SQL_SUMMARY = _YEAR_CTE + """
SELECT
    (SELECT y FROM yr)                                                                AS window_year,
    COUNT(*)                                                                          AS total_shipments,
    SUM(CASE WHEN fs.asn_sent_late THEN 1 ELSE 0 END)                                AS late_asn_count,
    SUM(CASE WHEN NOT fs.is_on_time THEN 1 ELSE 0 END)                               AS late_delivery_count,
    ROUND(SUM(CASE WHEN fs.asn_sent_late THEN 1 ELSE 0 END)::numeric / COUNT(*), 4)  AS asn_late_rate,
    ROUND(SUM(CASE WHEN fs.is_on_time THEN 1 ELSE 0 END)::numeric / COUNT(*), 4)     AS on_time_rate,
    SUM(CASE WHEN dr.retailer_name = 'Walmart' AND fs.asn_sent_late THEN 1 ELSE 0 END) AS walmart_late_asn
FROM public_marts.fct_retailer_shipments fs
JOIN public_marts.dim_retailers dr ON fs.retailer_id = dr.retailer_id
WHERE EXTRACT(YEAR FROM fs.ship_date) = (SELECT y FROM yr)
"""

_SQL_BY_RETAILER = _YEAR_CTE + """
SELECT
    dr.retailer_name,
    COUNT(*)                                                                          AS total_shipments,
    SUM(CASE WHEN fs.asn_sent_late THEN 1 ELSE 0 END)                                AS late_asn,
    ROUND(SUM(CASE WHEN fs.asn_sent_late THEN 1 ELSE 0 END)::numeric / COUNT(*), 4)  AS asn_late_rate,
    ROUND(SUM(CASE WHEN fs.is_on_time THEN 1 ELSE 0 END)::numeric / COUNT(*), 4)     AS on_time_rate
FROM public_marts.fct_retailer_shipments fs
JOIN public_marts.dim_retailers dr ON fs.retailer_id = dr.retailer_id
WHERE EXTRACT(YEAR FROM fs.ship_date) = (SELECT y FROM yr)
GROUP BY dr.retailer_name
ORDER BY late_asn DESC
"""

# Walmart OTIF by case, per month (anchor A5.16). Cases ordered = order-line
# units / case_pack_qty (order lines are whole cases). Cases delivered = whole
# cases received, capped at cases ordered (no receipt row -> units shipped).
# On time = delivered by MABD (requested_ship_date + mabd_days); lines with no
# delivery date yet are counted separately and left out of on-time.
_SQL_WALMART_OTIF = _YEAR_CTE + """,
lines AS (
    SELECT
        date_trunc('month', o.po_date)::date                              AS po_month,
        sl.units_ordered::numeric / p.case_pack_qty                        AS cases_ordered,
        floor(LEAST(COALESCE(rl.units_received, sl.units_shipped), sl.units_ordered)::numeric
              / p.case_pack_qty)                                           AS cases_delivered,
        CASE WHEN fs.delivery_date IS NOT NULL AND fs.requested_ship_date IS NOT NULL
             THEN fs.delivery_date <= fs.requested_ship_date + CAST(:mabd AS int)
        END                                                                AS arrived_by_mabd,
        fs.ship_date
    FROM public_marts.fct_retailer_shipment_lines sl
    JOIN public_marts.fct_retailer_shipments fs ON fs.shipment_id = sl.shipment_id
    JOIN public_marts.fct_retailer_orders o     ON o.order_id = sl.order_id
    JOIN public_marts.dim_retailers dr          ON dr.retailer_id = sl.retailer_id
    JOIN public_marts.dim_products p            ON p.sku = sl.sku
    LEFT JOIN public_marts.fct_retailer_receipt_lines rl
           ON rl.shipment_id = sl.shipment_id AND rl.sku = sl.sku
    WHERE dr.retailer_name = 'Walmart'
      AND EXTRACT(YEAR FROM o.po_date) = (SELECT y FROM yr)
)
SELECT
    po_month,
    SUM(cases_ordered)                                                     AS cases_ordered,
    SUM(cases_delivered)                                                   AS cases_delivered,
    SUM(CASE WHEN arrived_by_mabd THEN cases_delivered ELSE 0 END)         AS cases_on_time,
    SUM(CASE WHEN arrived_by_mabd IS NOT NULL THEN cases_ordered ELSE 0 END) AS cases_ordered_dated,
    SUM(CASE WHEN arrived_by_mabd IS NULL THEN 1 ELSE 0 END)               AS undated_lines,
    MIN(CASE WHEN arrived_by_mabd IS NULL THEN ship_date END)              AS undated_first_ship,
    MAX(CASE WHEN arrived_by_mabd IS NULL THEN ship_date END)              AS undated_last_ship
FROM lines
GROUP BY po_month
ORDER BY po_month
"""


class OtifExposureQuestion(BaseQuestion):
    def meta(self) -> QuestionMeta:
        return QuestionMeta(
            id="q13",
            question="Am I about to get hit with OTIF penalties I can't see?",
            short_label="OTIF penalty exposure?",
            source_piece="OTIF Blind Spot",
            go_deeper_link="https://lailarallc.com/otif-blind-spot",
            scenario="baseline",
        )

    def run(self) -> VerdictResponse:
        summary = query(_SQL_SUMMARY)[0]
        by_retailer = query(_SQL_BY_RETAILER)

        window_year = int(summary["window_year"])
        total_shipments = int(summary["total_shipments"] or 0)
        late_asn = int(summary["late_asn_count"] or 0)
        asn_late_rate = float(summary["asn_late_rate"] or 0)
        walmart_late_asn = int(summary["walmart_late_asn"] or 0)
        cfg = _CFG
        fee = cfg["penalty_per_asn_late"]

        months = query(_SQL_WALMART_OTIF, {"mabd": cfg["walmart_mabd_days"]})
        on_time_target = cfg["on_time_target_prepaid"]
        in_full_target = cfg["in_full_target"]
        cases_ordered = sum(float(m["cases_ordered"]) for m in months)
        cases_on_time = sum(float(m["cases_on_time"]) for m in months)
        wm_in_full = sum(float(m["cases_delivered"]) for m in months) / cases_ordered
        wm_on_time = cases_on_time / sum(float(m["cases_ordered_dated"]) for m in months)
        wm_on_time_undated_late = cases_on_time / cases_ordered
        n_months = len(months)
        months_passing = sum(
            1 for m in months
            if float(m["cases_delivered"]) / float(m["cases_ordered"]) >= in_full_target
            and float(m["cases_ordered_dated"])
            and float(m["cases_on_time"]) / float(m["cases_ordered_dated"]) >= on_time_target
        )
        all_months_pass = months_passing == n_months
        undated_lines = sum(int(m["undated_lines"]) for m in months)
        undated_ships = [d for m in months for d in (m["undated_first_ship"], m["undated_last_ship"]) if d]

        exposure = walmart_late_asn * fee
        worst_retailer = by_retailer[0] if by_retailer else None

        def _vs(rate, target):
            return "meets" if rate >= target else "misses"

        asn_fires = asn_late_rate > cfg["asn_late_rate_threshold"]
        otif_passes = wm_on_time >= on_time_target and wm_in_full >= in_full_target
        if otif_passes and all_months_pass:
            pass_clause = f", and both pass in all {n_months} months"
        else:
            pass_clause = (f"; for the year on-time {_vs(wm_on_time, on_time_target)} its target and in-full "
                           f"{_vs(wm_in_full, in_full_target)} its target, and both pass in "
                           f"{months_passing} of {n_months} months")
        exposure_clause = ("Walmart's exposure here is the ASN fee, not OTIF. "
                           if asn_fires and otif_passes and all_months_pass else "")
        delivery_note = (
            f"Scored Walmart's way (by case, arrival by MABD, POs dated {window_year}), Walmart on-time is "
            f"{wm_on_time:.1%} against its {on_time_target:.0%} prepaid target and in-full is "
            f"{wm_in_full:.1%} against {in_full_target:.0%}{pass_clause}. {exposure_clause}"
            f"Walmart also charges 3% of the cost of goods on late or short cases; "
            f"that fine is not included in this figure."
        )

        if asn_fires:
            verdict = (
                f"In {window_year}, {late_asn:,} of {total_shipments:,} shipments ({asn_late_rate:.1%}) had late ASNs. "
                f"Walmart charges ${fee:,} per late-ASN PO under SQEP: "
                f"{walmart_late_asn:,} Walmart late ASNs = ${exposure:,.0f} in {window_year}. "
                f"Other retailers' ASN fees are unknown and not counted. "
                f"Worst account: {worst_retailer['retailer_name']} at {float(worst_retailer['asn_late_rate']):.1%} late ASN rate. "
                f"{delivery_note}"
            )
            verdict_detail = f"{asn_late_rate:.1%} ASN late — ${exposure:,.0f} Walmart ASN fees ({window_year})"
        else:
            verdict = (
                f"ASN compliance is clean in {window_year}: {asn_late_rate:.1%} ASN late rate "
                f"(below the {cfg['asn_late_rate_threshold']:.0%} threshold) "
                f"across {total_shipments:,} shipments. {delivery_note}"
            )
            verdict_detail = "ASN compliant"

        if undated_lines:
            first, last = min(undated_ships), max(undated_ships)
            undated_note = (
                f"; {undated_lines:,} lines shipped {first:%b} {first.day}–{last:%b} {last.day} "
                f"with no delivery date yet are excluded (counting them as late gives "
                f"{wm_on_time_undated_late:.1%}, "
                f"{'still passing' if wm_on_time_undated_late >= on_time_target else 'below target'})"
            )
        else:
            undated_note = ""

        chart_data = ChartData(
            type="bar",
            title=f"Late ASN rate by retailer, {window_year}",
            data=[
                {
                    "retailer": r["retailer_name"],
                    "asn_late_rate": float(r["asn_late_rate"]),
                    "late_asn": int(r["late_asn"]),
                    "total_shipments": int(r["total_shipments"]),
                }
                for r in by_retailer
            ],
            x_key="retailer",
            y_key="asn_late_rate",
            unit="share",
        )

        return VerdictResponse(
            question_id="q13",
            question=self.meta().question,
            verdict=verdict,
            verdict_detail=verdict_detail,
            key_numbers=[
                KeyNumber(
                    label=f"Late ASN shipments, {window_year}",
                    value=f"{late_asn:,} of {total_shipments:,}",
                    context=f"{asn_late_rate:.1%} of all shipments",
                ),
                KeyNumber(
                    label=f"Walmart ASN fees, {window_year}",
                    value=f"${exposure:,.0f}",
                    context=f"{walmart_late_asn:,} Walmart late ASNs × ${fee:,}; other retailers excluded",
                ),
                KeyNumber(
                    label=f"Walmart OTIF, {window_year} (by case)",
                    value=f"{wm_on_time:.1%} on time · {wm_in_full:.1%} in full",
                    context=(f"Targets {on_time_target:.0%} (prepaid, by MABD) and {in_full_target:.0%}; "
                             + (f"met in all {n_months} months" if otif_passes and all_months_pass
                                else f"both met in {months_passing} of {n_months} months")),
                ),
            ],
            chart=chart_data,
            rule_explanation=(
                f"Walmart ASN fees = Walmart late-ASN shipments in {window_year} × ${fee:,} "
                f"(Walmart SQEP Phase 1 flat fee per late-ASN PO; each late-ASN shipment counted as one PO). "
                f"Other retailers' ASN fees are unknown and excluded. "
                f"Fires when the all-retailer asn_sent_late rate > {cfg['asn_late_rate_threshold']:.0%}. "
                f"Walmart OTIF targets since early 2024 (SPS Commerce; Walmart's own spec is in Retail Link): "
                f"{on_time_target:.0%} on-time for prepaid freight, measured at arrival by MABD (requested ship date + "
                f"{cfg['walmart_mabd_days']} days); 98% ready for collect pickup; {in_full_target:.0%} in-full, "
                f"scored as whole cases delivered against cases ordered. "
                f"Walmart charges 3% of the cost of goods on late or short cases. "
                f"The data has no prepaid/collect flag, so prepaid is assumed. "
                f"Walmart OTIF uses POs dated {window_year}{undated_note}. "
                f"Window: calendar {window_year}, the same year used in q15. "
                f"Late ASN = ASN arrived after ship date (asn_sent_late = true in fct_retailer_shipments)."
            ),
            go_deeper_link=self.meta().go_deeper_link,
            go_deeper_label=self.meta().source_piece,
            scenario=self.meta().scenario,
            source_piece=self.meta().source_piece,
        )


registry.register(OtifExposureQuestion())

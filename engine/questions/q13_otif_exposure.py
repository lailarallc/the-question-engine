"""
Q13: Am I about to get hit with OTIF penalties I can't see?

Reads fct_retailer_shipments for ASN compliance and on-time delivery over one
window: the last full calendar year, the same year q15 uses for working capital.

Rule: if asn_late_rate > ASN_LATE_RATE_THRESHOLD, fires with
exposure = Walmart late-ASN count × PENALTY_PER_ASN_LATE.

The $25/PO fee is Walmart's SQEP Phase 1 ASN defect fee, so only Walmart late
ASNs are priced. Other retailers' ASN fees are unknown and excluded (the page
says so). Walmart delivery is scored Walmart's way (arrival by MABD, units
received), matching the canonical otif block: on-time vs the 90% prepaid
target, in-full vs 95%. The OTIF fine (a % of COGS) is not dollarized here.

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

# Walmart OTIF scored the way Walmart does, replicating otif-blind-spot
# scripts/02_export_json.py (the canonical otif block): on time = delivered by
# MABD (requested_ship_date + mabd_days); in full = units received >= units
# ordered, with the same fallbacks (0 received -> units shipped; 0 ordered on
# lines -> PO total units). Periods by po_date, as in canonical.
_SQL_WALMART_OTIF = _YEAR_CTE + """,
sl AS (
    SELECT shipment_id, SUM(units_ordered) AS uo, SUM(units_shipped) AS us
    FROM public_marts.fct_retailer_shipment_lines
    GROUP BY shipment_id
),
rl AS (
    SELECT shipment_id, SUM(units_received) AS ur
    FROM public_marts.fct_retailer_receipt_lines
    GROUP BY shipment_id
),
w AS (
    SELECT
        fs.requested_ship_date,
        fs.delivery_date,
        COALESCE(fs.is_on_time, FALSE)                          AS is_on_time,
        COALESCE(NULLIF(sl.uo, 0), NULLIF(o.total_units, 0), 0) AS uo,
        COALESCE(NULLIF(rl.ur, 0), COALESCE(sl.us, 0))          AS ur
    FROM public_marts.fct_retailer_shipments fs
    JOIN public_marts.fct_retailer_orders o ON fs.order_id = o.order_id
    JOIN public_marts.dim_retailers dr ON fs.retailer_id = dr.retailer_id
    LEFT JOIN sl ON fs.shipment_id = sl.shipment_id
    LEFT JOIN rl ON fs.shipment_id = rl.shipment_id
    WHERE dr.retailer_name = 'Walmart'
      AND EXTRACT(YEAR FROM o.po_date) = (SELECT y FROM yr)
)
SELECT
    COUNT(*) AS shipments,
    AVG(CASE
            WHEN requested_ship_date IS NOT NULL AND delivery_date IS NOT NULL
            THEN (delivery_date <= requested_ship_date + CAST(:mabd AS int))::int
            ELSE is_on_time::int
        END) AS on_time_arrival_rate,
    AVG(CASE WHEN uo > 0 THEN (ur >= uo)::int ELSE 1 END) AS in_full_rate
FROM w
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
        on_time_rate = float(summary["on_time_rate"] or 0)
        walmart_late_asn = int(summary["walmart_late_asn"] or 0)
        cfg = _CFG
        fee = cfg["penalty_per_asn_late"]

        otif = query(_SQL_WALMART_OTIF, {"mabd": cfg["walmart_mabd_days"]})[0]
        wm_on_time = float(otif["on_time_arrival_rate"] or 0)
        wm_in_full = float(otif["in_full_rate"] or 0)
        on_time_target = cfg["on_time_target_prepaid"]
        in_full_target = cfg["in_full_target"]

        exposure = walmart_late_asn * fee
        worst_retailer = by_retailer[0] if by_retailer else None

        def _vs(rate, target):
            return "meets" if rate >= target else "misses"

        delivery_note = (
            f"Scored Walmart's way (arrival by MABD, POs dated {window_year}), Walmart on-time is "
            f"{wm_on_time:.1%} against its {on_time_target:.0%} prepaid target ({_vs(wm_on_time, on_time_target)}), "
            f"and in-full is {wm_in_full:.1%} against {in_full_target:.0%} ({_vs(wm_in_full, in_full_target)}). "
            f"The OTIF fine (3% of COGS on failing cases) is separate and not in this figure."
        )

        if asn_late_rate > cfg["asn_late_rate_threshold"]:
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
                    label=f"Shipped by requested date, {window_year}",
                    value=f"{on_time_rate:.1%}",
                    context=(f"All retailers, at the brand's dock. Walmart measures arrival: "
                             f"{wm_on_time:.1%} on time, {wm_in_full:.1%} in full"),
                ),
            ],
            chart=chart_data,
            rule_explanation=(
                f"Walmart ASN fees = Walmart late-ASN shipments in {window_year} × ${fee:,} "
                f"(Walmart SQEP Phase 1 flat fee per late-ASN PO; each late-ASN shipment counted as one PO). "
                f"Other retailers' ASN fees are unknown and excluded. "
                f"Fires when the all-retailer asn_sent_late rate > {cfg['asn_late_rate_threshold']:.0%}. "
                f"Walmart targets since 2024-02-01 (SPS Commerce; Walmart's own spec is in Retail Link): "
                f"{on_time_target:.0%} on-time for prepaid, measured at arrival by MABD (requested ship date + "
                f"{cfg['walmart_mabd_days']} days); 98% ready for collect pickup; {in_full_target:.0%} in-full "
                f"(every unit ordered was received). The data has no prepaid/collect flag, so prepaid is assumed. "
                f"Walmart OTIF uses POs dated {window_year}; the OTIF fine is not dollarized. "
                f"Window: calendar {window_year}, the same year used in q15. "
                f"Late ASN = ASN arrived after ship date (asn_sent_late = true in fct_retailer_shipments)."
            ),
            go_deeper_link=self.meta().go_deeper_link,
            go_deeper_label=self.meta().source_piece,
            scenario=self.meta().scenario,
            source_piece=self.meta().source_piece,
        )


registry.register(OtifExposureQuestion())

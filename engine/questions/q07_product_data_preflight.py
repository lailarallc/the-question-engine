"""
Q07: Is my product data going to break at a national mass retailer?

Checks four critical field categories against dim_products:
  - GTIN-14: must be non-null and exactly 14 digits
  - UPC: must be non-null and 12 or 13 digits
  - Weights: case_weight_lbs must be non-null and > 0
  - Dimensions: all three case dimensions must be non-null and > 0

Rule: if critical error rate > CRITICAL_ERROR_THRESHOLD, verdict is "do not submit."

Thresholds calibrated from Product Data Health Audit piece.
"""
import yaml
from pathlib import Path

from engine.base import BaseQuestion
from engine.registry import registry
from api.models.schemas import VerdictResponse, QuestionMeta, KeyNumber, ChartData
from db.connection import query

_CFG = yaml.safe_load(
    (Path(__file__).parent.parent.parent / "config" / "thresholds.yaml").read_text()
)["q07"]

_SQL = """
SELECT
    COUNT(*)                                                                       AS total_skus,
    COUNT(CASE WHEN gtin14 IS NULL OR gtin14 = '' OR LENGTH(TRIM(gtin14)) != 14
               OR gtin14 !~ '^[0-9]{14}$' THEN 1 END)                            AS gtin_errors,
    COUNT(CASE WHEN upc IS NULL OR upc = ''
               OR LENGTH(TRIM(upc)) NOT IN (12, 13)
               OR upc !~ '^[0-9]{12,13}$' THEN 1 END)                            AS upc_errors,
    COUNT(CASE WHEN case_weight_lbs IS NULL OR case_weight_lbs <= 0 THEN 1 END)   AS weight_errors,
    COUNT(CASE WHEN case_length_in  IS NULL OR case_length_in  <= 0
               OR case_width_in    IS NULL OR case_width_in    <= 0
               OR case_height_in   IS NULL OR case_height_in   <= 0 THEN 1 END)  AS dimension_errors,
    COUNT(DISTINCT CASE WHEN
               (gtin14 IS NULL OR gtin14 = '' OR LENGTH(TRIM(gtin14)) != 14 OR gtin14 !~ '^[0-9]{14}$')
            OR (upc IS NULL OR upc = '' OR LENGTH(TRIM(upc)) NOT IN (12, 13) OR upc !~ '^[0-9]{12,13}$')
            OR (case_weight_lbs IS NULL OR case_weight_lbs <= 0)
            OR (case_length_in IS NULL OR case_length_in <= 0
                OR case_width_in IS NULL OR case_width_in <= 0
                OR case_height_in IS NULL OR case_height_in <= 0)
        THEN sku END)                                                             AS skus_with_errors
FROM public_marts.dim_products
"""

_SQL_BAD_SKUS = """
SELECT
    sku,
    product_name,
    product_line,
    CASE WHEN gtin14 IS NULL OR gtin14 = '' OR LENGTH(TRIM(gtin14)) != 14 OR gtin14 !~ '^[0-9]{14}$'
         THEN 'GTIN-14 invalid' END AS gtin_issue,
    CASE WHEN upc IS NULL OR upc = '' OR LENGTH(TRIM(upc)) NOT IN (12, 13) OR upc !~ '^[0-9]{12,13}$'
         THEN 'UPC invalid' END AS upc_issue,
    CASE WHEN case_weight_lbs IS NULL OR case_weight_lbs <= 0
         THEN 'Weight missing' END AS weight_issue,
    CASE WHEN case_length_in IS NULL OR case_length_in <= 0
              OR case_width_in IS NULL OR case_width_in <= 0
              OR case_height_in IS NULL OR case_height_in <= 0
         THEN 'Dimensions incomplete' END AS dimension_issue
FROM public_marts.dim_products
WHERE
    (gtin14 IS NULL OR gtin14 = '' OR LENGTH(TRIM(gtin14)) != 14 OR gtin14 !~ '^[0-9]{14}$')
    OR (upc IS NULL OR upc = '' OR LENGTH(TRIM(upc)) NOT IN (12, 13) OR upc !~ '^[0-9]{12,13}$')
    OR (case_weight_lbs IS NULL OR case_weight_lbs <= 0)
    OR (case_length_in IS NULL OR case_length_in <= 0
        OR case_width_in IS NULL OR case_width_in <= 0
        OR case_height_in IS NULL OR case_height_in <= 0)
ORDER BY product_line, sku
LIMIT 20
"""


class ProductDataPreflightQuestion(BaseQuestion):
    def meta(self) -> QuestionMeta:
        return QuestionMeta(
            id="q07",
            question="Is my product data going to break at a national mass retailer?",
            short_label="Product data retailer-ready?",
            source_piece="Product Data Health Audit",
            go_deeper_link="https://lailarallc.com/product-data-health-audit",
            scenario="baseline",
        )

    def run(self) -> VerdictResponse:
        summary = query(_SQL)[0]
        bad_skus = query(_SQL_BAD_SKUS)  # LIMIT 20 — powers the example list only

        total = int(summary["total_skus"])
        gtin_err = int(summary["gtin_errors"])
        upc_err = int(summary["upc_errors"])
        weight_err = int(summary["weight_errors"])
        dim_err = int(summary["dimension_errors"])

        # Count DISTINCT failing SKUs across the whole catalog. Previously this
        # used len(bad_skus), which is capped by the LIMIT 20 example query and
        # silently under-reports the failure count once >20 SKUs are affected.
        skus_with_any_error = int(summary["skus_with_errors"])
        example_skus = [r["sku"] for r in bad_skus[:5]]
        critical_rate = skus_with_any_error / total if total > 0 else 0
        cfg = _CFG
        worst_field = max(
            [("GTIN-14", gtin_err), ("UPC", upc_err), ("Weight", weight_err), ("Dimensions", dim_err)],
            key=lambda x: x[1],
        )

        if critical_rate > cfg["critical_error_threshold"]:
            verdict = (
                f"{skus_with_any_error} of {total} SKUs ({critical_rate:.0%}) have data errors "
                f"that will fail a national mass retailer's GDSN submission. "
                f"Worst field: {worst_field[0]} with {worst_field[1]} errors. "
                f"Do not submit until these are resolved — "
                f"a failed GDSN sync delays item setup by weeks."
            )
            verdict_detail = "do not submit"
        elif critical_rate > cfg["warning_error_threshold"]:
            verdict = (
                f"{skus_with_any_error} of {total} SKUs ({critical_rate:.0%}) have data issues. "
                f"Below the do-not-submit threshold but above the warning level. "
                f"Fix {worst_field[0]} errors ({worst_field[1]} SKUs) before the next sync window."
            )
            verdict_detail = "fix before next sync"
        else:
            verdict = (
                f"Product data is clean: {critical_rate:.1%} error rate across {total} SKUs. "
                f"All critical fields — GTIN-14, UPC, weight, dimensions — "
                f"are within the {cfg['critical_error_threshold']:.0%} threshold. "
                f"Safe to submit."
            )
            verdict_detail = "safe to submit"

        chart_data = ChartData(
            type="bar",
            title="Data errors by field type",
            data=[
                {"field": "GTIN-14", "errors": gtin_err, "error_rate": gtin_err / total},
                {"field": "UPC", "errors": upc_err, "error_rate": upc_err / total},
                {"field": "Weight", "errors": weight_err, "error_rate": weight_err / total},
                {"field": "Dimensions", "errors": dim_err, "error_rate": dim_err / total},
            ],
            x_key="field",
            y_key="error_rate",
            unit="share",
        )

        return VerdictResponse(
            question_id="q07",
            question=self.meta().question,
            verdict=verdict,
            verdict_detail=verdict_detail,
            key_numbers=[
                KeyNumber(label="SKUs with errors", value=f"{skus_with_any_error} of {total}"),
                KeyNumber(label="Critical error rate", value=f"{critical_rate:.1%}"),
                KeyNumber(label="Worst field", value=f"{worst_field[0]}", context=f"{worst_field[1]} errors"),
            ],
            chart=chart_data,
            rule_explanation=(
                f"Failure count = COUNT(DISTINCT sku) with any critical-field error across all "
                f"{total} SKUs. Critical fields: GTIN-14 (14-digit numeric), UPC (12-13 digit numeric), "
                f"case weight (> 0), case dimensions (all three > 0). "
                f"Do-not-submit threshold: > {cfg['critical_error_threshold']:.0%} SKU error rate. "
                f"Warning: > {cfg['warning_error_threshold']:.0%}. "
                + (f"Example affected SKUs: {', '.join(example_skus)}. " if example_skus else "")
                + f"Thresholds from Product Data Health Audit."
            ),
            go_deeper_link=self.meta().go_deeper_link,
            go_deeper_label=self.meta().source_piece,
            scenario=self.meta().scenario,
            source_piece=self.meta().source_piece,
        )


registry.register(ProductDataPreflightQuestion())

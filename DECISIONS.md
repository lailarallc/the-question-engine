# DECISIONS — The Question Engine

---

## 2026-09-24 — Dollar figures are per-year for a named calendar year; retailer-specific fees stay with their retailer

**Decision:** A verdict's dollar figure is an actual count for one named window: the last full calendar year of data (`EXTRACT(YEAR FROM MAX(received_date) + 1) - 1` on `fct_retailer_payments`), shared by q13 and q15, and the page names that year. A fee or threshold that belongs to one retailer (Walmart SQEP $25/PO) is applied only to that retailer; retailers whose fee is unknown are excluded and the page says so.

**Why:** The rest of the portfolio states figures per year (e.g. short-ship's $298K/yr). A 3-year total next to annual figures reads as a smaller problem; dividing it by 3 is an estimate that won't survive a CFO's questions. Pricing all 6 retailers at Walmart's fee overstated q13 ~12× ($100,150 vs $8,175).

**Do not:** show multi-year totals as "current run rate"; annualize by dividing a multi-year total by N; apply one retailer's fee or floor to other retailers.

---

## 2026-09-24 — Metrics defined in canonical_values.json use the canonical computation

**Decision:** When `reference/canonical_values.json` defines a metric, the question computes it the way `cinderhaven-data-platform/sql/canonical_gather.sql` does, not with a local approximation. q15 DSO = order-value-weighted (received_date − po_date), each order matched to remittances received 25–55 days after the start of its PO month (= 25.58, canonical `dso_days.trailing_36m`).

**Why:** q15's own approximation (every delivery in the prior 90 days) produced ~45 days by construction and a working-capital figure ~5× the canonical-consistent one. Matching the canonical method makes the verdict reconcile to the portfolio's source of truth.

**Do not:** reintroduce the 90-day any-delivery DSO match, or divide a multi-year total by 365.

---

## 2026-09-24 — Database access for renders and diagnosis: tunnel on 15432, scoped to one process

**Decision:** Live-DB work (render_pdfs, read-only diagnosis) uses `fly proxy 15432:5432 -a cinderhaven-db`. DATABASE_URL is set to the 15432 URL only inside that one process (python-dotenv won't override an already-set var). No pytest while a tunnel is open. Close the tunnel immediately after and confirm `netstat -ano | findstr :15432` is empty.

**Why:** A tunnel left on 5432 let a test suite in another repo query production. This repo's `.env` points at `localhost:5432`, and `POSTGRES_PASSWORD` is set machine-wide, so anything on 5432 silently becomes production.

**Do not:** run `fly proxy` on 5432; leave a tunnel open between steps; rely on clearing env vars in this repo (dotenv reloads `.env`).

---

## 2026-06-12 — No bulk PDF download in v1; individual PDFs ungated

**Decision:** v1 ships per-question PDFs only (`GET /api/pdf/{question_id}`). No zip-all/bulk endpoint. Individual PDFs are open — no email gate.

**Why:** The PDFs exist to be shared one verdict at a time; a 13-file bundle serves scrapers more than readers. Email-gating is content-marketing machinery, and PLAN.md scopes all marketing surface to a separate process outside this repo. Not building the bulk endpoint *is* the gate.

**How to apply:** If bulk export demand appears, revisit as a deliberate v2 item with the gating question decided in the website/marketing context — not added here casually. *(Logged autonomously 2026-06-12 — flag for review.)*

---

## 2026-06-10 — Rules-based verdicts, not LLM

**Decision:** Every verdict is produced by explicit Python rules with documented YAML thresholds. No LLM at the verdict layer.

**Why:** The anti-LLM positioning is the product. Transparency ("here is exactly how this verdict was reached") is what differentiates the engine from every "ask your data" product that uses an LLM. Showing the rules and being uncopyable anyway is the flex.

**How to apply:** Do not introduce LLM calls into the verdict path. A v2 feature for natural-language question *matching* (routing free-text to the fixed 15) is acceptable — but the verdict itself must always be a deterministic rule.

---

## 2026-06-10 — Exactly fifteen questions, no more

**Decision:** The question count is fixed at 15. Resist adding question #16.

**Why:** Curation is the product. The list should feel deliberate, not exhaustive. Each question was chosen because it represents a recurring CEO anxiety backed by a shipped piece.

---

## 2026-06-10 — Scenario per question is explicit and documented

**Decision:** Each question declares its scenario (baseline or distressed) in `config/questions.yaml` and in the question module. Q04 (trade spend) uses distressed; all others baseline unless documented otherwise.

**Why:** Silently mixing canonical universes is the one unforgivable bug. Every figure shown must reconcile to its source piece, and source pieces use specific scenarios.

---

## 2026-06-10 — Q05 and Q06 are stubs until upstream pieces ship

**Decision:** Q05 (EDI reconciliation) and Q06 (recall blast radius) are `is_stub=True` and return 503 from the API.

**Why:** They depend on EDI Reconciliation v2 and Recall Blast Radius, neither of which has shipped. Building them now would require inventing data or mocking figures that don't reconcile to anything — exactly the bug we can't have.

---

## 2026-06-10 — Q11–Q15 topic selection

**Decision:** Stockout cost (Q11), Forecast accuracy (Q12), OTIF exposure (Q13), Velocity decay (Q14), Cash conversion (Q15).

**Why:** All five map to existing Cinderhaven mart tables with sufficient signal. Stockout and OTIF are direct financial exposures. Forecast accuracy and velocity decay are early-warning signals buyers act on before operators notice. Cash conversion explains the most common specialty food founder complaint ("sales are up but we have no cash").

---

## 2026-06-10 — Forecast proxy for Q12

**Decision:** Use `fct_distribution.avg_weekly_units` as the standing forecast in MAPE calculation — not a dedicated forecast table (none exists in Cinderhaven).

**Why:** No `fct_forecast` table exists in `public_marts`. The distribution average is the closest analog to what a planner would use as a baseline velocity assumption.

**How to apply:** If a forecast table is ever added to Cinderhaven, update Q12 to read from it. Until then, the proxy is documented in `rule_explanation`.

---

## 2026-06-10 — Q13 uses late ASN as OTIF signal, not delivery lateness

**Decision:** Q13 measures `asn_sent_late` rate, not `is_on_time` rate. Exposure = Walmart late ASNs in the last full calendar year × $25/PO (2025: 327 × $25 = $8,175).

**Correction (2026-09-23):** Originally $200/incident ($801,200). $200 is Walmart SQEP's DSDC/pharmacy "ASN Not Downloaded" fee, not Late ASN; SQEP Phase 1 charges a flat $25/PO for all other ASN defects, including Late ASN.

**Correction (2026-09-24):** The 09-23 figure ($100,150 = 4,006 × $25) applied Walmart's fee to late ASNs from all 6 retailers over 3 years. Now Walmart only, 2025 only (same window as q15): 327 × $25 = $8,175. Other retailers' ASN fees are unknown and excluded. The "zero late deliveries" premise below no longer holds: on-time is 95.7% overall / 95.9% Walmart (1,948 late deliveries), below the 98% floor; the verdict states this but does not dollarize the OTIF fine.

**Why:** In the Cinderhaven dataset, all 46,760 shipments have `is_on_time = true` (zero late deliveries). Late ASN is the only live OTIF signal — and it's the blind spot the question targets: Walmart counts late ASN as an OTIF violation even when product arrives on time.

---

## 2026-06-10 — Q14 uses 13-week vs prior 13-week window

**Decision:** Velocity decay measured as trailing 13 weeks vs weeks 14–26 (not 8 vs 8).

**Why:** The 8-week window captured Q4 2025 seasonal growth (+19–24%) for every SKU, masking any structural trend. The 13-week window provides a fuller quarter of comparison and is more aligned with how buyers review scan data.

---

## 2026-06-10 — Q15 DSO via 90-day delivery-to-payment window join

**Decision:** DSO = avg(received_date − delivery_date) joined by retailer_id with `delivery_date BETWEEN received_date − 90 AND received_date`.

**Why:** No direct order-to-payment key exists. The 90-day window matches each remittance to recent deliveries by the same retailer. This gives a ~44-day DSO consistent with standard Net-30/45 CPG terms.

---

## 2026-06-10 — Canonical deduction backlog is cross-channel; gate checks retailer-only

> Figures updated 2026-06-30: cross-channel backlog is **$1.35M** (16,917 rows), retailer-only ~$1.12M (14,947 rows). Original entry cited the pre-06-20-tuning $1.59M; the scope-separation decision below is unchanged.

**Decision:** The canonical "Deductions — total backlog $1.35M" covers all 9 trading partners (retailer + distributor). The Question Engine's q10 — and therefore `check_canonical.py` — validates only the retailer portion from `fct_retailer_deductions`. This is intentional scope separation, not drift.

**Why:** `fct_retailer_deductions` is a retailer-scoped mart by design. Distributor deductions live in a separate table. The gap between the cross-channel $1.35M and the retailer-only gate value is documented. Expanding q10 to include distributor data would require a separate question or a schema join not currently supported.

**Do not:** change the gate's expected value to the cross-channel $1.35M. The gate correctly validates the retailer-only scope. If a cross-channel deduction question is added, it gets its own check with its own expected value and explicit scope annotation.

---

## 2026-06-10 — Q01 is the reference implementation

**Decision:** Q01 (`engine/questions/q01_biggest_customer.py`) is the full pattern. All subsequent questions follow it exactly — YAML threshold loading, DB query, rule logic, VerdictResponse construction.

**Why:** Consistency makes the rules library readable and auditable. The repo being readable is part of the transparency pitch.

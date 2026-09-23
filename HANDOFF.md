# HANDOFF — The Question Engine

**Last updated:** 2026-07-10
**Session:** Session 7 — restored ask.lailarallc.com outage + reconstructed audit-fixes
**Phase:** Phase 5 maintenance — live at ask.lailarallc.com, verdicts + audit-fixes deployed

---

## 2026-07-10 — Session 7 (outage restore + audit-fixes)

**Outage:** every verdict returned "data source may be unavailable" (503). Root cause was two stacked DB-connection breakages — NOT a missing artifact, and DATABASE_URL *was* set:
1. `DATABASE_URL` used the legacy `postgres://` scheme (from `fly pg attach`); SQLAlchemy 2.x rejects it (`Can't load plugin: sqlalchemy.dialects:postgres`), so `create_engine()` threw before any query → the `except → 503` path fired for all verdicts.
2. cinderhaven-db credentials had desynced (its own `flypgadmin` monitor was failing md5 auth; the `postgres` role password no longer matched the app secret).

**Fixes (all deployed + pushed to main):**
- `db/connection.py` normalizes `postgres://`→`postgresql://` (durable guard against re-attach).
- Resynced cinderhaven-db `postgres`/`flypgadmin`/`repmgr` role passwords to their secret env values via the local **trust** socket (`psql -h /var/run/postgresql -p 5433 -U postgres`; real PG is on 5433). Repointed `ask-cinderhaven` `DATABASE_URL` to `SU_PASSWORD` (URL-encoded) via `fly secrets set`.
- See memory `question-engine-outage-postgres-scheme.md` for the full recovery playbook.

**Audit-fixes** — there was NO audit-fixes branch anywhere (confirmed: no local/remote branch, no dangling commits); reconstructed all 6 from spec and validated the verdict-changing ones against CINDERHAVEN_CANONICAL.md:
- Frontend: demoted brand/"Fifteen questions" hero → plain value prop; count now set dynamically to the 13 non-stub questions that render (`main.js` #question-count); `#fde8e7`→`#fce8e7`; self-hosted Playfair Display + Source Sans 3 (woff2 under `/fonts/`, `@font-face`, no CDN).
- q07: failing-SKU count now `COUNT(DISTINCT sku)` (was `len(bad_skus)` capped by LIMIT 20). Before 20/50 (40%) → after **21/50 (42%)**, dimensions worst (19). LIMIT 20 kept for the example-SKU list.
- q02: relabeled promo "payback/ROI" → **revenue-coverage months** (a liquidity proxy, not profit). Verdict now cites the canonical Cost of Saying Yes launch model (net cash Year 1 **−$36,320** on **$499,200** gross). Chose the relabel (reconcilable) over a contribution-margin ROI, which couldn't reconcile to the single modeled-launch figure.
- Follow-ups: self-hosted D3 (`/vendor/d3.min.js` v7.9.0, dropped jsdelivr CDN); registered `font/woff2` MIME in `api/main.py`.

**Verified in browser:** hero demoted, "Pick one of 13 questions", Playfair renders; q01 + q02 verdicts render (verdict + 3 numbers + chart) with vendored D3; fonts serve `font/woff2`.

**Commits:** `a512eb9` (scheme) → `1937231` (d3+mime), pushed to origin/main. Tests 15/15.

**Note:** live verdict figures differ from the Session-6 table below (data retuned post-06-20); e.g. q09 now "all channels positive", q15 12.7% drag. That's current-data drift, not a regression.

---

## What was done this session

- Implemented all 8 live question modules end-to-end:
  - Q01 biggest_customer, Q02 retailer_launch_cost, Q03 sku_rationalization
  - Q04 trade_spend (distressed scenario), Q07 product_data_preflight
  - Q08 weight_cost, Q09 channel_profitability, Q10 deduction_recovery
- **Schema fix**: All modules originally used `marts.` as table prefix; actual schema in Cinderhaven PostgreSQL is `public_marts`. Fixed with find/replace across all 8 modules.
- **Q02 promo filter fix**: `WHERE funding_mechanism = 'manufacturer'` returned zero rows (no such value exists). All four mechanism types (billback, MCB, off_invoice, scan_based) are manufacturer-side cost. Removed filter; fixed `< 1 month` display.
- All 8 tests pass: `pytest tests/ -v` → 8 passed
- DB access: `fly proxy 5432 -a cinderhaven-db` (must be running for verdicts to work)

## All 15 live verdict results from Cinderhaven data

| Q | Verdict detail | Headline |
|---|---|---|
| q01 | healthy | Largest account 21% revenue, 2% deduction rate |
| q02 | all launches affordable | Fastest payback < 1 month, 176x ROI |
| q03 | no kills | All 50 SKUs above velocity/margin floors |
| q04 | within range | 12% unplanned deductions (ceiling 25%) |
| q07 | **do not submit** | 40% of SKUs fail Walmart GDSN (dimensions worst) |
| q08 | $142K realized + $264K projected | 3 of 50 SKUs have weight data gaps |
| q09 | **2 channels negative** | Distributor + Retailer lose money; DTC +$442K |
| q10 | **money left + broken process** | 61% expired deductions, win rate below 50% |
| q11 | **$4.6M implied stockout cost** | 144,790 zero-velocity store-weeks at authorized locations |
| q12 | **43.9% MAPE — forecast broken** | Forecast errors > 30% threshold; worst SKU needs investigation |
| q13 | **8.6% ASN late — $100,150 exposure** | 4,006 late ASNs × $25/PO; all deliveries on time but ASN process is the gap. *2026-09-23: was $801K at $200/incident — $200 is the DSDC "ASN Not Downloaded" fee, not Late ASN.* |
| q14 | all SKUs accelerating | Portfolio +36.2% avg; slowest is Everything Bagel Spread at +24.7% |
| q15 | **13.2% deduction drag** | $6.8M deducted from $52M invoiced; DSO ~44 days |

---

## 2026-06-10 — Session 4

**Started from:** Phase 3 canonical reconciliation. Gate skeleton existed but unpopulated.

**Did:**
- Populated `scripts/check_canonical.py` with 7 checks (q01 share, q03 SKU count, q10 row stability + backlog + recovery rate, q13 ASN late rate, q15 deduction drag)
- First run had 4 failures; fixed SQL grouping error in q01, wrong chargeback count assumption, wrong recovery rate metric (model field vs realized)
- Investigated cross-channel vs retailer portion — found clean scope split: retailer portion + distributor portion = canonical cross-channel total (was $1.59M / 16,023 rows at the time; **now $1.35M / 16,917 rows after the 06-20 deduction tuning**)
- Updated gate with scope note; annotated CINDERHAVEN_CANONICAL.md with full breakdown
- Gate passes 7/7

**State:** Gate green. CINDERHAVEN_CANONICAL.md annotated. No deploy yet. PLAN.md Phase 3 marked complete.

**Next:** `fly deploy` to ask.lailarallc.com → smoke-test all 15 verdicts on production → Phase 5 promotion tasks.

---

## Known issues / blockers

- Q05 (EDI reconciliation) and Q06 (recall cost) are deliberately stubbed — blocked on unshipped source pieces. Do not implement.
- q09 shows $420M negative contribution margin for Retailer + Distributor channels — correct from the synthetic Cinderhaven data at scale; not a bug.
- Q11 uses `fct_distribution.weeks_with_sales` as a zero-velocity proxy. If fct_distribution is not refreshed regularly, stockout cost figures will lag reality.
- `fct_retailer_deductions` has zero "open" deductions in baseline — all are expired or disputed. q10's `open_amount` is always 0; potential_recovery will always be 0 until data is refreshed with open deductions.

## 2026-06-11 — Session 5

**Did:**
- Created `Dockerfile` (python:3.13-slim + uvicorn) and `.dockerignore`
- Fixed pydantic version: 2.7.4 had no cp313 wheels; bumped to `>=2.9,<3`
- Created Fly app `ask-cinderhaven`, set `DATABASE_URL` secret (cinderhaven-db.flycast internal network)
- Changed `fly.toml` region from `ord` to `iad` (co-located with DB)
- Resolved q12 OOM: `fct_scan_data` is 1.4M rows; `PERCENTILE_CONT` over 1.4M rows OOM-kills the DB machine; rewrote to GROUP BY sku first (50 groups, AVG only, no global sort), compute stats in Python from 50 rows
- Added `idx_scan_sku_store` index on `fct_scan_data(sku, store_id)` for join performance
- Deployed and smoke-tested: 13/13 live verdicts pass, q05/q06 return 503 stub as expected

**State:** Live at https://ask.lailarallc.com. 13/13 verdicts verified on production. Custom domain cert issued. q12 runs ~40s (acceptable for v1).

## 2026-06-11 — Session 6

**Did:**
- Committed Dockerfile, `.dockerignore`, `fly.toml` (region iad), relaxed pydantic version — all deploy prep from session 5
- Fixed `materialize_q12.py`: by-SKU query was re-joining `fct_distribution` against 1.38M error rows (timeout). Fixed by pulling `forecast_units` from within the errors CTE. Also set `statement_timeout=0` and `work_mem=128MB`
- Added `remat_q12_by_sku.py` for targeted by-SKU refresh without re-running summary
- Ran `materialize_q12.py` to populate `q12_summary` / `q12_by_sku` (but deployed q12 module doesn't use these — it runs `_SQL_ALL_SKUS` GROUP BY SKU directly; pre-computed tables are unused)
- Confirmed `ask.lailarallc.com` cert already issued; domain live
- Smoke-tested all 15 verdicts on production: 13/13 pass, q05/q06 return 503

## 2026-06-11 — Session 7

**Started from:** Phase 5 in-progress — gate had passed 7/7 (Session 4) but deploy blocked by DB proxy not running locally.

**Did:**
- Ran `fly deploy` — all Docker layers cached (Depot), image 70 MB, deployed to `ask-cinderhaven` machine `48ee562a363508`; machine reached started state cleanly
- Smoke-tested all 15 verdict endpoints via POST: q01–q04 + q07–q15 return HTTP 200; q05/q06 return HTTP 503 (stubs) — correct
- Spot-checked q10 verdict body: real Cinderhaven data ($809K expired deductions, retailer breakdown by 6 accounts) — data pipeline confirmed end-to-end
- Discovered `ask.lailarallc.com` cert status is **Not verified** — Fly shows no AAAA records in DNS. Previous HANDOFF entries claiming domain live were premature; DNS records were never actually added.
- Identified DNS is on Cloudflare (nameservers: garret/linda.ns.cloudflare.com)
- Attempted computer-use to navigate Cloudflare dashboard — timed out
- No Cloudflare API token stored locally (no `~/.wrangler`, no `CF_API_TOKEN` env var)
- User will paste Cloudflare API token next session; I'll call the API to add A + AAAA records

**DNS records needed (Fly → Cloudflare):**
- `A    ask.lailarallc.com → 66.241.124.8`
- `AAAA ask.lailarallc.com → 2a09:8280:1::126:1158:0`

**State:** App deployed and verified at `https://ask-cinderhaven.fly.dev`. Domain `ask.lailarallc.com` cert registered on Fly but DNS not pointed — domain not yet live on custom URL.

**Next:** User pastes Cloudflare API token → add A + AAAA records via API → cert verifies (usually <5 min) → custom domain live → update PLAN.md Phase 5 custom domain task to ✅

---

## What's next

1. **DNS** — paste Cloudflare token; I'll call the API to add A + AAAA records for ask.lailarallc.com
2. **Homepage CTA** — update lailara-website hero to `ask.lailarallc.com`
3. **/work page** — reorganize around the engine
4. **LinkedIn content calendar** — 15 posts, one per question
5. **Quarto one-pagers** — template at `quarto/_template.qmd`; render pipeline not built (Phase 4, can ship later)

---

## How to start the server

```
# Terminal 1 — DB proxy (must be running)
fly proxy 5432 -a cinderhaven-db

# Terminal 2 — API server
cd the-question-engine
python -m uvicorn api.main:app --port 8000 --reload
```

Then hit `http://localhost:8000` for the frontend, or `POST http://localhost:8000/api/verdict/q01`.

---

## File map

| File | Purpose |
|---|---|
| `engine/questions/q01_biggest_customer.py` | Reference implementation — read before writing any new question |
| `config/thresholds.yaml` | All rule thresholds — edit here only |
| `config/questions.yaml` | Master question manifest |
| `scripts/check_canonical.py` | Release gate — populate expected values from CINDERHAVEN_CANONICAL.md |
| `tests/test_engine.py` | Rule logic unit tests |

# PLAN — The Question Engine

**Tier:** Heavy (portfolio front door / capstone, maintained > 3 months)
**Status:** Phases 1–5 complete — live at ask.lailarallc.com, 13 verdicts + 13 one-pager PDFs
**Priority:** Maintenance — no open work arc

---

## Completion criteria

Phase 4 complete when: every non-stub registered question (currently 13; Q05/Q06 stubs excluded) renders to a one-page PDF via the parameterized Quarto template; rendering is reproducible via a single script/make target; PDFs are delivered as pre-rendered static artifacts served by the app (a `GET /api/pdf/{question_id}` endpoint returning pre-built files from `static/pdfs/`).

This project does not touch the lailara-website repo. Website surfacing and content marketing are handled through a separate process.

---

## Current focus

Maintenance. All phases complete: 13/13 verdicts pass at ask.lailarallc.com; q05/q06 stub 503 (awaiting the EDI reconciliation + recall source pieces); q12 ~40s acceptable for v1; one-pager PDFs served at /api/pdf/{id}. Re-run `make pdfs` + redeploy when canonical data or verdicts change.

---

## Task list

### Phase 1 — Infrastructure ✅
- [x] Scaffold project structure
- [x] FastAPI app + verdict router
- [x] BaseQuestion abstract class + registry pattern
- [x] YAML thresholds config
- [x] DB connection (read-only)
- [x] Frontend shell (HTML/CSS/JS + D3)
- [x] Quarto one-pager template
- [x] check_canonical.py release gate skeleton
- [x] Unit tests

### Phase 2 — Question implementation ✅
- [x] Q01: Should I fire my biggest customer?
- [x] Q02: Can I afford this retailer launch?
- [x] Q03: Which SKUs should die?
- [x] Q04: Where is my trade spend going? (distressed)
- [x] Q05: EDI reconciliation — STUB
- [x] Q06: Recall blast radius — STUB
- [x] Q07: Product data preflight
- [x] Q08: Weight cost
- [x] Q09: Channel profitability
- [x] Q10: Deduction recovery
- [x] Q11: Stockout cost
- [x] Q12: Forecast accuracy
- [x] Q13: OTIF exposure
- [x] Q14: Velocity decay
- [x] Q15: Cash conversion

### Phase 3 — Canonical reconciliation ✅
- [x] Populate check_canonical.py expected values from CINDERHAVEN_CANONICAL.md
- [x] Run gate and fix any drift (7/7 pass; $1.35M scope documented)
- [x] Verify: every figure shown reconciles to its source piece

### Phase 4 — One-pagers + export ✅
- [x] Quarto render pipeline per question ✓ — 2026-06-12 (`make pdfs` → scripts/render_pdfs.py; 13/13 non-stub questions render to static/pdfs/; key-numbers table + verdict detail added to template)
- [x] PDF download endpoint ✓ — 2026-06-12 (`GET /api/pdf/{question_id}`; 404 unknown/unrendered, 503 stubs; 4 tests, suite 12/12)
- [x] Bulk download gating — DECIDED 2026-06-12: no bulk endpoint in v1, individual PDFs ungated (see DECISIONS.md)

### Phase 5 — Deploy + promote
- [x] `fly deploy` → https://ask-cinderhaven.fly.dev (2026-06-11)
- [x] Smoke-test all 15 verdicts on production (13 pass, 2 stubs 503 as expected)
- [x] Custom domain: ask.lailarallc.com — live (CNAME → fly app, cert Issued 2026-06-11)
- ~~Homepage hero CTA takeover~~ — REMOVED: handled outside this project
- ~~_/work page reorganizes around the engine~~ — REMOVED: handled outside this project
- ~~LinkedIn content calendar~~ — REMOVED: handled outside this project

---

## Open questions

1. Final name: *Ask Cinderhaven* vs question-as-title
2. LLM natural-language question matching in v2? Lean pure select for v1.

---

## Out of scope (v1)

- Free-text question input / LLM interpretation
- User-uploaded data
- More than fifteen questions
- Any new data generation

---

## Improvement History

### 2026-09-23 — Audit (health check only)
- **Findings:** 3 critical, 5 important, 4 nice-to-have
- **Top concerns:** q13 verdict (re-rendered today) says "the ASN process is the only gap" while showing 95.8% on-time delivery against its own 98% floor, and applies Walmart's $25/PO SQEP fee to every retailer's shipments. q04 shows "$0 manufacturer promo spend" because it still filters `funding_mechanism = 'manufacturer'` (the zero-row bug fixed in q02 on 2026-06-10). q15 DSO of 44 days contradicts canonical ~25.5 days; the 90-day window join averages ~45 days by construction and also drives the $6.29M working-capital figure.
- **Important:** q04 is labeled "distressed" but has no scenario filter (its $1,118,682 total is the baseline retailer backlog) and its unplanned-type substring match likely misses short_ship/spoilage; production DATABASE_URL uses the Postgres superuser behind unauthenticated POST endpoints with no caching or rate limit (q12 ~40s over 1.4M rows); fly-deploy runs on every push with no test/preflight gate and check_canonical covers only 7 figures (no DSO, q04, or q13 dollars); q11 counts pre-authorization weeks as stockouts and its rule_explanation describes a check the code does not do; HANDOFF.md header/What's-next are stale (2026-07-10, DNS/Quarto items long done) and there is no project CLAUDE.md.
- **Nice:** stale remote branch origin/client-mode-2026-08 (all 3 commits re-applied to main); orphan .claude/worktrees/lucid-tharp-ce06d6 (730K, not a registered worktree) and .dockerignore does not exclude .claude/; pytest/httpx ship in the prod image while ruff is undeclared, and `preflight` is missing from .PHONY; q13 docstring says 95% floor vs 98% in yaml, unused otif_rate, unused q12 materialize scripts.
- **Verification:** tests 15/15 pass (no DB); canonical drift gate clean; findings in q04/q13/q15 confirmed against committed static/pdfs text. Manual security/code/SQL pass replaced /security-review, /ce:review, and data-science-reviewer. No database connections made.
- **Action taken:** Audit only — no fixes this session
- **Next review:** 2026-10-21

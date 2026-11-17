# The Question Engine

Fifteen questions every specialty food brand CEO asks, each answered in 30 seconds with a rules-based verdict, one chart, and the three numbers behind it.

**Live:** https://ask.lailarallc.com

## What it does

The CEO picks a question; the engine runs documented rules against the Cinderhaven mart layer and returns a verdict (one sentence, opinionated), the one chart that justifies it, the three numbers behind it, and a link into the deep-dive portfolio piece. Fifteen questions, each a doorway.

Deliberately not an LLM. Every verdict is produced by explicit, readable rules with documented thresholds (`config/thresholds.yaml`) — transparency is the product.

| # | Question | Source piece |
|---|---|---|
| Q01 | Should I fire my biggest customer? | Retailer Scorecard |
| Q02 | Can I afford this retailer launch? | Cost of Saying Yes |
| Q03 | Which SKUs should die? | SKU Rationalization |
| Q04 | Where is my trade spend going? | Trade Spend Diagnostic |
| Q05 | Why don't my numbers match my distributor's? | EDI Reconciliation (stub) |
| Q06 | What would a recall cost me? | Recall Blast Radius (stub) |
| Q07 | Is my product data going to break at a national mass retailer? | Product Data Health Audit |
| Q08 | What does one wrong weight cost? | Dimension & Weight Integrity |
| Q09 | Which channel actually makes money? | Channel Profitability |
| Q10 | Am I leaving deduction money on the table? | Deduction Recovery |
| Q11 | What are stockouts costing me? | Stockout Cost |
| Q12 | How accurate are my forecasts? | Forecast Accuracy |
| Q13 | What is my OTIF exposure? | OTIF Exposure |
| Q14 | Which SKUs are losing velocity? | Velocity Decay |
| Q15 | What is my cash conversion cycle? | Cash Conversion |

13 verdicts live; Q05 and Q06 link out to their now-live source tools (reconcile.lailarallc.com, recall.lailarallc.com) — their API verdicts intentionally 503 until native verdicts ship.

## Why it matters

Executives don't want dashboards; they want answers to the questions they already have. Each verdict compresses a full analytical deliverable into a 30-second experience, and each links to the deep-dive piece behind it — a low-friction front door to the entire portfolio. Because every threshold is documented and every rule is readable code, the reasoning behind each verdict can be audited line by line.

Built on the Cinderhaven synthetic dataset — a ~$25M specialty food brand, 50 SKUs across 5 product lines and 6 contracted retailers. Data is synthetic; methodology and deliverables are real.

## Quick start

```bash
git clone https://github.com/MsShawnP/the-question-engine.git
cd the-question-engine
cp .env.example .env
# edit .env — set DATABASE_URL to your Cinderhaven Postgres instance
pip install -r requirements.txt
make dev
# → http://localhost:8000
```

Other targets (see `Makefile`):

```bash
make test             # pytest suite
make check-canonical  # every displayed figure must reconcile to its source piece
make preflight        # release gate: check-canonical + test — run before every deploy
make pdfs             # render one-pagers to static/pdfs/ (needs DATABASE_URL + Quarto)
make lint             # ruff
```

Deploy: `fly deploy` (container defined in `Dockerfile`, config in `fly.toml`).

## Tech stack

- **Python 3.13** — FastAPI + Uvicorn
- **Rules engine** — one module per question (`engine/questions/q01…q15`), YAML thresholds (`config/thresholds.yaml`)
- **Frontend** — vanilla JS + D3, no build step (`frontend/`)
- **One-pagers** — Quarto templates rendered to PDF (`quarto/`, `make pdfs`)
- **Data** — Postgres / dbt: reads existing Cinderhaven marts, no new models
- **Deploy** — Fly.io (API) + Cloudflare (DNS)
- **Dev** — pytest, pytest-asyncio, httpx, ruff

## Project structure

```
api/       FastAPI app, routers (verdict, pdf), response schemas
engine/    Verdict rules: base.py, registry.py, questions/q01–q15
config/    questions.yaml (catalog), thresholds.yaml (documented cut-offs)
frontend/  Static UI (index.html, src/, styles/)
quarto/    One-pager templates
scripts/   check_canonical.py (reconciliation gate), render_pdfs.py, utilities
tests/     pytest suite
```

## Data contract

**Canonical baseline:** 50 SKUs · 5 product lines (AS·PS·SC·DG·SB) · 6 retailers (Walmart·Costco·Whole Foods·Sprouts·Kroger·Regional Group) · 10 channels (6 retail + UNFI·KeHE·DPI + DTC)

Every figure shown reconciles to its source piece via `scripts/check_canonical.py`. An inconsistency breaks the entire portfolio's coherence — it is the one unforgivable bug.

## License

MIT

---

Built by [Lailara LLC](https://lailarallc.com) — data hygiene and analytics consulting for specialty food brands scaling into national retail.

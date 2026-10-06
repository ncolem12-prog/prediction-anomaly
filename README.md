# Prediction Market Anomaly Detector

A prototype anomaly detection pipeline built on Polymarket's public trade data. It flags trades that are statistically unusual for their market, scored in dollars, and surfaces them in a deployed dashboard. A flag means "unusual," not "insider trading." See Corrections and Honest Limitations below.

**Live dashboard:** https://prediction-anomaly.vercel.app

---

## What It Does

Ingests trade data from Polymarket's public API, converts each trade to dollars (shares × price), scores it with per-market z-scores, and flags the outliers.

**Three flag types:**
- **Size:** the trade is unusually large in dollars relative to that market's other trades (threshold: 2.5σ)
- **Timing:** the trade was placed in the final 7 days before the market's scheduled end date, and unusually late relative to that market's other trades (threshold: 2.0σ)
- **Confluence:** both size and timing elevated at once (threshold: 1.5σ each)

Per-market normalization means a $500 trade in a thin market scores differently than a $500 trade in a deep one.

**Units.** Polymarket's `size` field is a quantity of outcome shares, and `price` is dollars per share (0 to 1). Every dollar figure in this project is `size × price`. 10,000 shares at $0.02 is a $200 trade.

**Timing.** Polymarket's `endDate` is the scheduled end date, not the actual resolution time. Markets can keep trading past it. Trades placed after the scheduled end date receive no timing score.

---

## What the Metrics Mean

**Flag rate**
The percentage of trades flagged. It is a property of the thresholds, not a measure of accuracy.

**Flagged volume share**
The percentage of total dollar volume carried by flagged trades. A high number says flagged trades are large. It does not say they are informed: size flags are large by construction, so this number is expected to be high and is not evidence that the detector finds real signal.

**Mean flagged trade vs. mean unflagged trade**
How much larger flagged trades are in dollars. Same caveat as above.

**Interpretation note**
These are descriptive statistics about detector output, not accuracy metrics. Without ground truth labels, precision and recall cannot be computed. Current numbers are on the live dashboard.

---

## Corrections (October 2026)

A review of the flagged trades themselves, not just the flag counts, found two errors in the original version. Both are fixed. Numbers below are for the same sample: 20,000 trades across 28 markets, fetched May to July 2026.

**1. Share counts were reported as dollars.** The pipeline treated Polymarket's `size` field (shares) as a dollar amount. Dollars are `size × price`.

**2. Trades after the scheduled end date were scored as "late."** Six markets kept trading after their scheduled end date. All 6,000 of their trades had a negative time-to-close, which the timing score ranked as the latest possible. 194 of the 212 timing flags and 42 of the 47 confluence flags were these trades. Timing flags now require a trade to fall in the final 7 days before the scheduled end date.

| Metric | Originally published | Corrected |
|---|---|---|
| Total flags | 496 (2.5%) | 284 (1.4%) |
| Size flags | 237 | 284 |
| Timing flags | 212 | 0 |
| Confluence flags | 47 | 0 |
| Total volume | "$2.85M" (shares) | $808,813 |
| Mean flagged trade | "$3,092" (shares) | $1,459 |
| Mean unflagged trade | "$68" (shares) | $20 |
| Flagged share of volume | 53.8% (of shares) | 51.2% (of dollars) |

**What changed in the conclusions.** In this sample, no trade qualifies as a timing or confluence flag, so the composite "large and late" signal has no supporting examples yet. The detector as it stands finds large trades. Whether any of them are informed is untested.

**How it was caught.** The original evaluation counted flags and summed volume. It never read the flagged rows. Reading the top flagged trades showed the problem within a few queries. Reading a sample of flagged rows is now part of the evaluation checklist (`docs/specs/`).

---

## Architecture

Polymarket API
↓
fetch.py: pulls 500 recent trades per market, stores in SQLite
↓
detect.py: converts to dollars, computes per-market z-scores, writes flags
↓
evaluate.py: generates report + exports static data.json
↓
dashboard/public/data.json: committed to GitHub
↓
Vercel: serves Next.js dashboard, auto-redeploys on push

---

## Stack

| Layer | Technology |
|---|---|
| Data pipeline | Python, Pandas, NumPy, SQLite |
| API | Polymarket REST (public, no auth) |
| Dashboard | Next.js, TypeScript, Tailwind CSS |
| Deployment | Vercel (auto-deploy from GitHub) |
| Version control | GitHub |

---

## Project Structure

prediction-anomaly/
├── pipeline/
│ ├── fetch.py # pulls trades from Polymarket API
│ ├── detect.py # z-score detection engine
│ └── evaluate.py # evaluation report + JSON export
├── dashboard/
│ ├── app/
│ │ ├── page.tsx # dashboard UI
│ │ └── api/anomalies/
│ │ └── route.ts # local API route
│ └── public/
│ └── data.json # static data file Vercel reads
├── data/
│ └── anomaly.db # local SQLite (not committed)
├── vercel.json # Vercel build config
├── run_pipeline.sh # one-command daily refresh
└── .gitignore

---

## Running It Locally

**Requirements:** Python 3.9+, Node.js 18+

**1. Clone the repo**
```bash
git clone https://github.com/ncolem12-prog/prediction-anomaly.git
cd prediction-anomaly
```

**2. Install Python dependencies**
```bash
python3 -m pip install requests pandas numpy scipy
```

**3. Run the pipeline**
```bash
bash run_pipeline.sh
```

**4. Start the dashboard**
```bash
cd dashboard
npm install
npm run dev
```

Open `http://localhost:3000`

---

## Daily Refresh

```bash
bash run_pipeline.sh
```

Fetches fresh data, detects anomalies, and exports `dashboard/public/data.json`. Commit and push that file, and Vercel redeploys automatically. The refresh is run manually; it is not scheduled yet.

---

## Honest Limitations

This is a prototype, not a production system. Key gaps documented explicitly:

**Statistical assumptions that are violated:**
- Bet size distributions are right-skewed (closer to log-normal than normal), which inflates false positives on legitimate large trades
- Stationarity not enforced. Baselines shift as markets age and attract different traders.
- No independence assumption. Coordinated multi-bet patterns from a single wallet evade detection entirely.

**Failure modes:**
- **False negative:** A wallet placing 50 bets of $1,200 each (total $60,000) before resolution. Each individual bet is unremarkable. The system has no velocity detection or wallet aggregation.
- **False positive:** A market maker placing a large liquidity order. Size z-score would be extreme. No role classification exists to distinguish makers from informed traders.

**Data and signal gaps:**
- The timing signal is anchored to the scheduled end date, which is not when a market actually resolves. A better anchor is the market's largest price move or its actual resolution time.
- Each market's baseline is its 500 most recent trades at fetch time, not its full history.
- Markets are the API's default top 20 active markets, not markets chosen because inside information is plausible.
- Market outcomes are not stored, so there is no check on whether a flagged trade was on the winning side.
- Dollar size ignores odds. A large purchase at $0.99 risks a lot to win very little and is unlikely to be an informed bet, but it scores the same as a large purchase at $0.05.
- Buys and sells are scored the same way.

**Evaluation gaps:**
- No ground truth labels, so precision and recall cannot be computed
- Flag rate and volume concentration are descriptive statistics, not accuracy metrics
- Thresholds (2.5σ, 2.0σ, 1.5σ) set by intuition, not empirical validation

**Production gaps:**
- No drift detection or threshold recalibration
- Batch pipeline, not real-time scoring
- No calibrated probabilities. All flags are binary.
- No monitoring or alerting on pipeline failures

---

## Phase 2 (Planned)

- **Outcome backtest:** store how markets resolve and test whether flagged trades were early and on the winning side
- **Market selection:** focus on markets where someone could plausibly know the answer early
- **Wallet pattern tracking:** flag wallets appearing in anomalous trades across multiple markets
- **Anomaly persistence:** track markets flagged across multiple daily fetches
- **Price movement validation:** check if flagged trades predict market price movement within 1 hour
- **Manual labeling interface:** enable true precision/recall computation
- **Expand market coverage:** currently 20 markets, API supports hundreds

---

## Why This Exists

Built as a hands-on exploration of production ML system design: problem framing, signal design, evaluation methodology, and the gap between a working prototype and a trustworthy system. The evaluation layer's explicit documentation of its own limitations is intentional. A system that can't explain its failure modes isn't ready for decisions.

---

## Author

Nicole Myers, Senior AI Product Operator. Building in compliance-heavy B2B SaaS through [Foundry AI Ops](https://github.com/ncolem12-prog).

[LinkedIn](https://linkedin.com/in/nicole-myers-msaa-ba67711b) · [GitHub](https://github.com/ncolem12-prog)

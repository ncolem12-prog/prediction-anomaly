# Prediction Market Anomaly Detector

A production-structured anomaly detection pipeline built on live Polymarket data. Flags statistically unusual trades across size, timing, and confluence signals. Results surface in a deployed dashboard updated daily.

**Live dashboard:** https://prediction-anomaly.vercel.app

---

## What It Does

Ingests live trade data from Polymarket's public API, scores each transaction using per-market z-scores across two independent signals, and flags anomalous behavior automatically.

**Three signal types:**
- **Size:** bet is unusually large relative to that market's baseline (threshold: 2.5σ)
- **Timing:** bet placed unusually close to market resolution (threshold: 2.0σ)
- **Confluence:** both size and timing elevated simultaneously (threshold: 1.5σ each). Rarest flag, highest signal strength.

Per-market normalization ensures a $500 bet in a $5,000 market scores differently than a $500 bet in a $10,000,000 market.

---

## What the Metrics Mean

**Flag rate (typically 1-3%)**
The percentage of trades flagged as anomalous. Too high means thresholds are too loose and the system is noisy. Too low means thresholds are too strict and real signals are being missed. 1-3% is the target range for this type of detector.

**Flagged volume share (typically 40-50%)**
The percentage of total dollar volume represented by flagged trades. If 1-3% of trades represent 40-50% of volume, flagged trades are systematically large, not randomly distributed. This is the strongest evidence the detector is finding real signal rather than noise.

**Mean flagged bet vs. mean normal bet**
The ratio between these two numbers shows how much larger flagged trades are on average relative to normal trading behavior. A 40-50x ratio is typical in this dataset, meaning the system is consistently identifying the largest actors in each market.

**Confluence flags**
The rarest flag type. Trades that are both unusually large AND unusually late simultaneously. Typically 10-20% of all flags. These are the highest-priority signals for human review because they require two independent conditions to be true at once.

**Interpretation note**
These are descriptive statistics about detector output, not accuracy metrics. Without ground truth labels, precision and recall cannot be computed. See Honest Limitations below.

---

## Architecture

Polymarket API
↓
fetch.py: pulls 500 recent trades per market, stores in SQLite
↓
detect.py: computes per-market z-scores, writes anomaly flags
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

Fetches fresh data, detects anomalies, exports JSON, pushes to GitHub. Vercel redeploys automatically. Live URL updates within 30 seconds.

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

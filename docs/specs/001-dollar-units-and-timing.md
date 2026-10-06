# Spec 001: Dollar units (F1) and timing signal (F2)

Status: implemented on branch `fix/dollar-units-and-timing` (Oct 5, 2026) with default decisions. Nicole to confirm or change section 4.
Owner: Nicole Myers
Related issues: (add GitHub issue numbers once created)

---

## 1. Problem (Nicole writes)

<!-- Who is hurt by this today, and how? Think about the two audiences:
     people reading the post/README/dashboard, and the detector itself. -->

## 2. Evidence (Claude gathered; check it)

Sample: 20,000 trades, 28 markets, fetched May to July 2026.

F1, units:
- Polymarket docs define `size` as "Trade quantity" and `price` as "Trade price per unit". Dollars = size x price.
- Total volume: $808,813 in dollars (published as "$2.85M", which was shares).

F2, timing:
- 6,000 of 20,000 trades (30%) have negative `minutes_to_close`. All 6,000 are the six Weinstein sentencing markets (scheduled end 2025-12-31, still trading July 2026).
- 194 of 212 timing flags and 42 of 47 confluence flags were those trades.
- 0 trades in the sample were placed within 24 hours before a scheduled end date. 2,573 were within 7 days.
- In markets with a future end date, the old timing score ranked the most recent trade in the fetch window as "latest", even with years to go.

Before and after (same sample):

| Metric | Before | After |
|---|---|---|
| Total flags | 496 (2.5%) | 284 (1.4%) |
| Size / Timing / Confluence | 237 / 212 / 47 | 284 / 0 / 0 |
| Mean flagged trade | "$3,092" (shares) | $1,459 |
| Mean unflagged trade | "$68" (shares) | $20 |
| Flagged share of volume | 53.8% (shares) | 51.2% (dollars) |

New finding from reading the flagged rows:
- 121 of the 284 flags (43%) are trades at a price of $0.95 or higher: large purchases of a near-certain outcome. These are probably not informed bets. Dollar size alone ignores odds.
- 104 of the 284 flags are sells.

## 3. Outcome and how we'll know (Nicole writes)

<!-- Not "ship the fix". What must be true afterwards?
     Write it so a query can check it. -->

## 4. Decisions (Nicole decides; Claude challenges)

Defaults Claude used so the fix could ship. Change any of these:
- Size z-score runs on dollars, no log transform.
- Trades after the scheduled end date: no timing score, excluded from the timing baseline, still eligible for size flags, shown as "after end date".
- Timing and confluence flags require the trade to fall in the final 7 days before the scheduled end date (`TIMING_WINDOW_DAYS` in detect.py).
- Timing and confluence stay in the product even though they currently fire 0 times.

F1:
- [ ] Should the size z-score run on dollars or on shares? (Hint: a 10,000-share bet at 2 cents is $200. Is that interesting for insider detection or not?)
- [ ] Log-transform dollars before scoring, or leave that for later (N5)?
- [ ] Where do corrected numbers get published: README, case study, LinkedIn post, dashboard? In what order?

F2:
- [ ] What happens to post-endDate trades: exclude from scoring, exclude from the baseline too, or keep as their own labeled category?
- [ ] Do we keep a timing signal at all until N4 (timing vs. price move), or turn it off?
- [ ] Does confluence survive if timing is off?

## 5. Alternatives considered (Nicole writes, at least two per fix)

## 6. Out of scope

- Full trade history (F3), market resolution (F4), market filter (N1).

## 7. Eval: checks that must pass before merge (draft together)

- [ ] 0 timing or confluence flags with minutes_to_close < 0 (or: they are labeled separately).
- [ ] Dashboard and README dollar figures equal sum(size x price) queries on the DB.
- [ ] Before/after table of flag counts by type, committed with the PR.
- [ ] Read the top 20 flagged trades by hand and note what they are.

## 8. Risks

<!-- What could this fix break or hide? -->

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime

DB_PATH = "data/anomaly.db"

# ── Thresholds ───────────────────────────────────────────────────
# These are the knobs we can tune later based on results.
# Z-score = how many standard deviations above the market's average.
# A z-score of 2.5 means the bet is 2.5 std devs above normal for
# that specific market — not globally, per market.

SIZE_THRESHOLD   = 2.5   # flag if bet size z-score exceeds this
TIMING_THRESHOLD = 2.0   # flag if timing z-score exceeds this
CONFLUENCE_MIN   = 1.5   # flag if BOTH scores exceed this (weaker individually, stronger together)
MIN_TRADES       = 5     # skip markets with fewer than this — not enough baseline

# A trade only counts as "late" if it was placed BEFORE the market's scheduled
# end date and within this many days of it. Without this gate, the most recent
# trade in a market that closes in 2028 scores as "late", which is meaningless.
TIMING_WINDOW_DAYS = 7
TIMING_WINDOW_MIN  = TIMING_WINDOW_DAYS * 24 * 60


# ── Z-score calculation ───────────────────────────────────────────

def compute_zscores(series):
    """
    Z-score formula: (value - mean) / standard_deviation

    This tells us how unusual each value is RELATIVE TO ITS OWN MARKET.
    A $500 bet might be normal in a $10M market but extreme in a $5K market.
    Per-market z-scores handle that automatically.

    Returns NaN when there aren't enough trades to compute a baseline.
    """
    if len(series) < MIN_TRADES:
        return pd.Series([np.nan] * len(series), index=series.index)
    mean = series.mean()
    std  = series.std()
    if std == 0:
        # All values identical — no variance, no anomaly possible
        return pd.Series([0.0] * len(series), index=series.index)
    return (series - mean) / std


# ── Main detection logic ─────────────────────────────────────────

def detect_anomalies():
    conn = sqlite3.connect(DB_PATH)

    trades_df  = pd.read_sql("SELECT * FROM trades",  conn)
    markets_df = pd.read_sql("SELECT * FROM markets", conn)

    conn.close()

    if trades_df.empty:
        print("No trades found. Run fetch.py first.")
        return

    print(f"Loaded {len(trades_df)} trades across {markets_df.shape[0]} markets.")

    # ── Units ────────────────────────────────────────────────────
    # Polymarket's `size` is a quantity of outcome shares, not dollars.
    # `price` is dollars per share (0 to 1). Dollars at risk = size x price.
    # 10,000 shares at $0.02 is a $200 trade, not a $10,000 trade.
    trades_df["usd_size"] = trades_df["size"] * trades_df["price"]

    # Trades placed after the scheduled end date. Polymarket's `endDate` is the
    # scheduled date, not the actual resolution time, so a market can keep
    # trading past it. These trades have no meaningful "time to close".
    trades_df["after_end_date"] = (trades_df["minutes_to_close"] < 0).astype(int)

    results = []

    for condition_id, group in trades_df.groupby("condition_id"):
        group = group.copy()
        n = len(group)

        if n < MIN_TRADES:
            print(f"  Skipping {condition_id[:10]}... — only {n} trades (need {MIN_TRADES})")
            continue

        # ── Signal 1: Size anomaly ───────────────────────────────
        # Is this bet unusually large IN DOLLARS for this specific market?
        group["size_zscore"] = compute_zscores(group["usd_size"])

        # ── Signal 2: Timing anomaly ─────────────────────────────
        # Is this bet placed unusually close to market close?
        # We INVERT minutes_to_close so that "late" = high z-score.
        # A bet placed 10 minutes before close has a small minutes_to_close
        # value, so negating it gives a large number — which z-scores high.
        #
        # Only trades placed BEFORE the scheduled end date get a timing score,
        # and the baseline is built from those trades only. Trades after the
        # end date get NaN (not applicable), so they can never be timing flags.
        before_end = group["minutes_to_close"] >= 0
        group["timing_zscore"] = np.nan
        if before_end.sum() >= MIN_TRADES:
            group.loc[before_end, "timing_zscore"] = compute_zscores(
                -group.loc[before_end, "minutes_to_close"]
            )
        in_window = before_end & (group["minutes_to_close"] <= TIMING_WINDOW_MIN)

        # ── Signal 3: Anomaly flag ───────────────────────────────
        # Three ways to get flagged:
        # 1. Size alone is very high
        # 2. Timing alone is very high (very late bet)
        # 3. Both are moderately high (confluence — the most interesting case)
        size_flag       = group["size_zscore"]   > SIZE_THRESHOLD
        timing_flag     = in_window & (group["timing_zscore"] > TIMING_THRESHOLD)
        confluence_flag = (
            in_window &
            (group["size_zscore"]   > CONFLUENCE_MIN) &
            (group["timing_zscore"] > CONFLUENCE_MIN)
        )

        group["anomaly_type"] = "none"
        group.loc[size_flag,                          "anomaly_type"] = "size"
        group.loc[timing_flag,                        "anomaly_type"] = "timing"
        group.loc[confluence_flag,                    "anomaly_type"] = "confluence"
        group.loc[size_flag & timing_flag,            "anomaly_type"] = "confluence"

        group["is_anomaly"] = (
            size_flag | timing_flag | confluence_flag
        ).astype(int)

        results.append(group)

    if not results:
        print("No markets had enough trades to analyze.")
        return

    final_df = pd.concat(results, ignore_index=True)

    # ── Write results back to DB ─────────────────────────────────
    conn = sqlite3.connect(DB_PATH)

    # Add columns if they don't exist yet
    for ddl in (
        "ALTER TABLE trades ADD COLUMN anomaly_type TEXT DEFAULT 'none'",
        "ALTER TABLE trades ADD COLUMN usd_size REAL",
        "ALTER TABLE trades ADD COLUMN after_end_date INTEGER DEFAULT 0",
    ):
        try:
            conn.execute(ddl)
            conn.commit()
        except Exception:
            pass  # column already exists, that's fine

    # Reset every trade first, so trades in markets we skipped (too few trades)
    # don't keep stale flags from an earlier run.
    conn.execute('''
        UPDATE trades
        SET usd_size       = size * price,
            after_end_date = CASE WHEN minutes_to_close < 0 THEN 1 ELSE 0 END,
            size_zscore    = NULL,
            timing_zscore  = NULL,
            is_anomaly     = 0,
            anomaly_type   = 'none'
    ''')
    conn.commit()

    cursor = conn.cursor()
    updated = 0
    for _, row in final_df.iterrows():
        cursor.execute('''
            UPDATE trades
            SET size_zscore   = ?,
                timing_zscore = ?,
                is_anomaly    = ?,
                anomaly_type  = ?
            WHERE id = ?
        ''', (
            None if pd.isna(row.get("size_zscore"))   else float(row["size_zscore"]),
            None if pd.isna(row.get("timing_zscore")) else float(row["timing_zscore"]),
            int(row.get("is_anomaly", 0)),
            row.get("anomaly_type", "none"),
            row["id"]
        ))
        updated += 1

    conn.commit()
    conn.close()

    # ── Print summary ────────────────────────────────────────────
    total   = len(final_df)
    flagged = final_df["is_anomaly"].sum()

    print(f"\n{'='*50}")
    print(f"DETECTION COMPLETE")
    print(f"{'='*50}")
    print(f"Total trades analyzed : {total}")
    print(f"Anomalies flagged     : {int(flagged)} ({100*flagged/total:.1f}%)")
    print()

    # Breakdown by type
    type_counts = final_df[final_df["is_anomaly"]==1]["anomaly_type"].value_counts()
    print("Breakdown by anomaly type:")
    for atype, count in type_counts.items():
        print(f"  {atype:<15} {count}")

    print()
    print("Top 10 anomalies by size z-score:")
    print("-" * 70)

    top = (
        final_df[final_df["is_anomaly"] == 1]
        .sort_values("size_zscore", ascending=False)
        .head(10)
    )

    # Get market questions for display
    conn = sqlite3.connect(DB_PATH)
    markets_df = pd.read_sql("SELECT condition_id, question FROM markets", conn)
    conn.close()

    top = top.merge(markets_df, on="condition_id", how="left")

    for _, row in top.iterrows():
        print(f"  Market  : {str(row.get('question', ''))[:55]}")
        print(f"  Size    : ${row['usd_size']:>10.2f}  ({row['size']:,.0f} shares @ ${row['price']:.3f}, z={row['size_zscore']:.2f})")
        if row["after_end_date"]:
            print(f"  Timing  : placed after scheduled end date (no timing score)")
        else:
            tz = "n/a" if pd.isna(row["timing_zscore"]) else f"{row['timing_zscore']:.2f}"
            print(f"  Timing  : {row['minutes_to_close']/1440:.1f} days to scheduled end  (z={tz})")
        print(f"  Type    : {row['anomaly_type']}")
        print(f"  Side    : {row['side']} {row['outcome']}")
        print()


if __name__ == "__main__":
    detect_anomalies()
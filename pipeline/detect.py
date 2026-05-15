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

    results = []

    for condition_id, group in trades_df.groupby("condition_id"):
        group = group.copy()
        n = len(group)

        if n < MIN_TRADES:
            print(f"  Skipping {condition_id[:10]}... — only {n} trades (need {MIN_TRADES})")
            continue

        # ── Signal 1: Size anomaly ───────────────────────────────
        # Is this bet unusually large for this specific market?
        group["size_zscore"] = compute_zscores(group["size"])

        # ── Signal 2: Timing anomaly ─────────────────────────────
        # Is this bet placed unusually close to market close?
        # We INVERT minutes_to_close so that "late" = high z-score.
        # A bet placed 10 minutes before close has a small minutes_to_close
        # value, so negating it gives a large number — which z-scores high.
        if group["minutes_to_close"].notna().sum() >= MIN_TRADES:
            group["timing_zscore"] = compute_zscores(-group["minutes_to_close"])
        else:
            group["timing_zscore"] = np.nan

        # ── Signal 3: Anomaly flag ───────────────────────────────
        # Three ways to get flagged:
        # 1. Size alone is very high
        # 2. Timing alone is very high (very late bet)
        # 3. Both are moderately high (confluence — the most interesting case)
        size_flag       = group["size_zscore"]   > SIZE_THRESHOLD
        timing_flag     = group["timing_zscore"] > TIMING_THRESHOLD
        confluence_flag = (
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

    # Add anomaly_type column if it doesn't exist yet
    try:
        conn.execute("ALTER TABLE trades ADD COLUMN anomaly_type TEXT DEFAULT 'none'")
        conn.commit()
    except Exception:
        pass  # column already exists, that's fine

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
        print(f"  Size    : ${row['size']:>10.2f}  (z={row['size_zscore']:.2f})")
        print(f"  Timing  : {row['minutes_to_close']:.0f} min to close  (z={row['timing_zscore']:.2f})")
        print(f"  Type    : {row['anomaly_type']}")
        print(f"  Side    : {row['side']} {row['outcome']}")
        print()


if __name__ == "__main__":
    detect_anomalies()
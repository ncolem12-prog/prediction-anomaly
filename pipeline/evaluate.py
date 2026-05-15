import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime

DB_PATH = "data/anomaly.db"

def evaluate():
    """
    Evaluation report for our anomaly detection system.

    IMPORTANT CONTEXT:
    True precision/recall requires ground truth labels —
    meaning we'd need to know which trades were ACTUALLY anomalous
    (insider information, bot activity, manipulation).

    We don't have those labels. Nobody publicly releases them.

    So we measure what we CAN measure honestly:
    1. Flag rates overall and per market
    2. Flag rates by anomaly type
    3. Size distribution of flagged vs normal trades
    4. Whether flagged trades cluster around certain markets
    5. What % of total volume flagged trades represent

    In an interview, you say: "I built the detection and evaluation
    framework. True precision/recall requires labeled ground truth
    we don't have access to. Here's what I can measure, here's what
    I'd need to measure the rest, and here's why that matters."
    """

    conn = sqlite3.connect(DB_PATH)

    trades_df  = pd.read_sql("SELECT * FROM trades",  conn)
    markets_df = pd.read_sql("SELECT condition_id, question, volume, volume_24hr FROM markets", conn)

    conn.close()

    if trades_df.empty:
        print("No trades. Run fetch.py and detect.py first.")
        return

    # Merge market names in
    df = trades_df.merge(markets_df, on="condition_id", how="left")

    total    = len(df)
    flagged  = df["is_anomaly"].sum()
    normal   = total - flagged

    print()
    print("=" * 60)
    print("EVALUATION REPORT")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # ── Section 1: Overall flag rate ─────────────────────────────
    print()
    print("1. OVERALL FLAG RATE")
    print("-" * 40)
    print(f"   Total trades     : {total:,}")
    print(f"   Flagged          : {int(flagged):,}  ({100*flagged/total:.1f}%)")
    print(f"   Normal           : {int(normal):,}  ({100*normal/total:.1f}%)")
    print()
    print("   Interpretation:")
    print("   A flag rate of 1-5% is typical for anomaly detection.")
    print("   Too high = thresholds too loose (too much noise).")
    print("   Too low  = thresholds too strict (missing real signals).")

    # ── Section 2: Flag rate by anomaly type ─────────────────────
    print()
    print("2. FLAG RATE BY ANOMALY TYPE")
    print("-" * 40)
    flagged_df = df[df["is_anomaly"] == 1]
    type_counts = flagged_df["anomaly_type"].value_counts()
    for atype, count in type_counts.items():
        pct = 100 * count / flagged
        print(f"   {atype:<15} {count:>4}  ({pct:.1f}% of flags)")

    # ── Section 3: Size comparison ───────────────────────────────
    print()
    print("3. BET SIZE: FLAGGED vs NORMAL")
    print("-" * 40)
    flagged_sizes = df[df["is_anomaly"] == 1]["size"]
    normal_sizes  = df[df["is_anomaly"] == 0]["size"]

    print(f"   {'':20} {'FLAGGED':>10}  {'NORMAL':>10}")
    print(f"   {'Mean bet size':20} ${flagged_sizes.mean():>9.2f}  ${normal_sizes.mean():>9.2f}")
    print(f"   {'Median bet size':20} ${flagged_sizes.median():>9.2f}  ${normal_sizes.median():>9.2f}")
    print(f"   {'Max bet size':20} ${flagged_sizes.max():>9.2f}  ${normal_sizes.max():>9.2f}")
    print(f"   {'Min bet size':20} ${flagged_sizes.min():>9.2f}  ${normal_sizes.min():>9.2f}")

    # ── Section 4: Volume concentration ─────────────────────────
    print()
    print("4. DOLLAR VOLUME IN FLAGGED TRADES")
    print("-" * 40)
    total_volume   = df["size"].sum()
    flagged_volume = flagged_df["size"].sum()
    print(f"   Total volume in dataset : ${total_volume:>12,.2f}")
    print(f"   Volume in flagged trades: ${flagged_volume:>12,.2f}")
    print(f"   Flagged volume share    : {100*flagged_volume/total_volume:.1f}%")
    print()
    print("   Interpretation:")
    print("   If 1.9% of trades represent a large % of volume,")
    print("   these aren't random noise — they're large actors.")

    # ── Section 5: Flag rate per market ──────────────────────────
    print()
    print("5. FLAG RATE BY MARKET")
    print("-" * 40)
    market_stats = df.groupby("question").agg(
        total_trades  = ("id", "count"),
        flagged_trades = ("is_anomaly", "sum"),
        avg_size      = ("size", "mean"),
        max_size      = ("size", "max")
    ).reset_index()
    market_stats["flag_rate"] = (
        market_stats["flagged_trades"] / market_stats["total_trades"] * 100
    )
    market_stats = market_stats.sort_values("flag_rate", ascending=False)

    for _, row in market_stats.iterrows():
        bar = "█" * int(row["flag_rate"])
        print(f"   {str(row['question'])[:45]:<45} "
              f"{row['flag_rate']:>5.1f}%  {bar}")

    # ── Section 6: Honest limitations ───────────────────────────
    print()
    print("6. HONEST LIMITATIONS")
    print("-" * 40)
    print("""
   What this report CANNOT tell you:
   - Whether flagged trades were actually manipulative
   - False positive rate (we have no ground truth labels)
   - False negative rate (we don't know what we missed)

   What would make this better:
   - Manual review of top 20 flagged trades
   - Track price movement after each flag (did the market
     move sharply in the flagged direction within 1 hour?)
   - Compare flagged wallets across multiple markets
     (same wallet anomalous in 3+ markets = stronger signal)
   - Label a sample manually and compute true precision/recall

   This is standard in production anomaly detection —
   you build the detection layer first, then invest in
   labeling infrastructure once you know the signal is real.
   """)

    print("=" * 60)
    print("END OF REPORT")
    print("=" * 60)
    print()

    # Return metrics dict for dashboard use later
    return {
        "total_trades"    : total,
        "flagged"         : int(flagged),
        "flag_rate"       : round(100 * flagged / total, 2),
        "flagged_volume"  : round(flagged_volume, 2),
        "total_volume"    : round(total_volume, 2),
        "volume_pct"      : round(100 * flagged_volume / total_volume, 2),
        "type_breakdown"  : type_counts.to_dict()
    }


if __name__ == "__main__":
    evaluate()
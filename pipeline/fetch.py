import requests
import sqlite3
import json
import time
from datetime import datetime, timezone

DB_PATH = "data/anomaly.db"
GAMMA_URL = "https://gamma-api.polymarket.com"
DATA_URL  = "https://data-api.polymarket.com"

# ── Database setup ──────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS markets (
            condition_id    TEXT PRIMARY KEY,
            question        TEXT,
            end_date        TEXT,
            volume          REAL,
            volume_24hr     REAL,
            clob_token_ids  TEXT,
            resolved        INTEGER DEFAULT 0,
            outcome         TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id                  TEXT PRIMARY KEY,
            condition_id        TEXT,
            side                TEXT,
            outcome             TEXT,
            size                REAL,
            price               REAL,
            timestamp           TEXT,
            minutes_to_close    REAL,
            size_zscore         REAL,
            timing_zscore       REAL,
            is_anomaly          INTEGER DEFAULT 0,
            FOREIGN KEY (condition_id) REFERENCES markets(condition_id)
        )
    ''')

    conn.commit()
    conn.close()
    print("Database ready.")


# ── Fetching markets ─────────────────────────────────────────────

def fetch_active_markets(limit=20):
    try:
        response = requests.get(
            f"{GAMMA_URL}/markets",
            params={"limit": limit, "closed": "false", "active": "true"},
            timeout=10
        )
        response.raise_for_status()
        markets = response.json()
        print(f"Fetched {len(markets)} active markets.")
        return markets
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return []


def save_markets(markets):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    saved = 0
    for m in markets:
        c.execute('''
            INSERT OR IGNORE INTO markets
                (condition_id, question, end_date, volume, volume_24hr, clob_token_ids)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            m.get("conditionId"),
            m.get("question"),
            m.get("endDate"),
            m.get("volumeNum"),
            m.get("volume24hr"),
            m.get("clobTokenIds")
        ))
        if c.rowcount > 0:
            saved += 1
    conn.commit()
    conn.close()
    print(f"Saved {saved} new markets to DB.")


# ── Fetching trades ──────────────────────────────────────────────

def fetch_trades_for_market(condition_id, limit=500):
    """
    Pull trades from the data API using conditionId directly.
    No auth required. Returns a list of trade dicts.
    """
    try:
        response = requests.get(
            f"{DATA_URL}/trades",
            params={"market": condition_id, "limit": limit},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        # API returns a list directly
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"  Error fetching trades: {e}")
        return []


def calculate_minutes_to_close(unix_timestamp, end_date_str):
    """
    Convert Unix timestamp + ISO end date into minutes-before-close.
    
    Unix timestamp = seconds since Jan 1, 1970.
    We convert both to UTC datetime objects and subtract.
    """
    try:
        trade_time = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
        end_time   = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        delta_minutes = (end_time - trade_time).total_seconds() / 60
        return max(delta_minutes, 0)
    except Exception:
        return None


def save_trades(trades, condition_id, end_date):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    saved = 0
    for t in trades:
        unix_ts  = t.get("timestamp")
        minutes  = calculate_minutes_to_close(unix_ts, end_date or "")
        # Convert Unix timestamp to readable string for storage
        try:
            ts_str = datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat()
        except Exception:
            ts_str = str(unix_ts)

        c.execute('''
            INSERT OR IGNORE INTO trades
                (id, condition_id, side, outcome, size, price, timestamp, minutes_to_close)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            t.get("transactionHash"),   # unique ID per trade
            condition_id,
            t.get("side"),
            t.get("outcome"),
            float(t.get("size", 0)),
            float(t.get("price", 0)),
            ts_str,
            minutes
        ))
        if c.rowcount > 0:
            saved += 1
    conn.commit()
    conn.close()
    return saved


# ── Main run ─────────────────────────────────────────────────────

def run_fetch():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting fetch...")

    markets = fetch_active_markets(limit=20)
    if not markets:
        print("No markets returned.")
        return

    save_markets(markets)

    total_trades = 0

    for market in markets:
        condition_id = market.get("conditionId")
        end_date     = market.get("endDate")
        question     = market.get("question", "")

        print(f"\n  Market: {question[:55]}")

        trades = fetch_trades_for_market(condition_id)
        if trades:
            saved = save_trades(trades, condition_id, end_date)
            total_trades += saved
            print(f"    {len(trades)} trades fetched, {saved} new saved")
        else:
            print(f"    No trades returned")

        time.sleep(0.3)

    print(f"\nFetch complete. Total new trades saved: {total_trades}")


if __name__ == "__main__":
    init_db()
    run_fetch()
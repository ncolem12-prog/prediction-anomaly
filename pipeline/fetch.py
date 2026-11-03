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
            proxy_wallet        TEXT,
            size_zscore         REAL,
            timing_zscore       REAL,
            is_anomaly          INTEGER DEFAULT 0,
            anomaly_type        TEXT DEFAULT 'none',
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

MAX_TRADES_PER_MARKET = 5000   # cap per market so one huge market can't take forever


def fetch_trades_for_market(condition_id, max_trades=MAX_TRADES_PER_MARKET):
    """
    Download a market's trades from Polymarket's Data API v2.

    v2 sends trades one page at a time. Each page includes a bookmark
    (next_cursor). We keep asking for the next page until there is no
    bookmark left, or until we reach max_trades.
    """
    trades = []
    params = {"condition": condition_id, "limit": 1000}

    while len(trades) < max_trades:
        try:
            response = requests.get(f"{DATA_URL}/v2/trades", params=params, timeout=15)
            response.raise_for_status()
            body = response.json()
        except Exception as e:
            print(f"  Error fetching trades: {e}")
            break

        if isinstance(body, list):
            page, next_cursor = body, None
        else:
            page = body.get("data") or body.get("trades") or body.get("results") or []
            next_cursor = (body.get("pagination") or {}).get("next_cursor")
            if not page and not trades:
                # Debugging help: if we found nothing, show what Polymarket sent back
                print(f"  No trades found. Response keys: {list(body.keys())}")

        trades.extend(page)

        if not next_cursor:
            break

        # Ask for the next page. Keep the same filter; the bookmark remembers the rest.
        params = {"condition": condition_id, "cursor": next_cursor}
        time.sleep(0.2)   # be polite to the API between pages

    return trades[:max_trades]


def calculate_minutes_to_close(unix_timestamp, end_date_str):
    """
    How many minutes before market close was this trade placed?
    
    We handle two edge cases:
    - Negative result means trade was placed AFTER market closed (rare but happens)
    - None means we couldn't parse the dates
    """
    try:
        trade_time = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
        end_time   = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        delta_minutes = (end_time - trade_time).total_seconds() / 60
        # Allow negative values through — they're meaningful
        # (trade placed after close = settlement trade, interesting signal)
        return round(delta_minutes, 2)
    except Exception:
        return None


def pick(record, *names):
    """
    Return the first field that exists in a trade record.
    v2 spells fields in snake_case (proxy_wallet); v1 used camelCase
    (proxyWallet). Trying both means either version works.
    """
    for name in names:
        value = record.get(name)
        if value is not None:
            return value
    return None


def save_trades(trades, condition_id, end_date):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    saved = 0

    for t in trades:
        tx_hash = pick(t, "transaction_hash", "transactionHash")
        unix_ts = pick(t, "timestamp")

        # Skip records we can't use: no ID, or no usable time
        if not tx_hash:
            continue
        try:
            unix_ts = int(unix_ts)
        except (TypeError, ValueError):
            continue

        minutes = calculate_minutes_to_close(unix_ts, end_date or "")
        ts_str  = datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat()

        c.execute('''
            INSERT OR IGNORE INTO trades
                (id, condition_id, side, outcome, size, price,
                 timestamp, minutes_to_close, proxy_wallet)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            tx_hash,
            condition_id,
            pick(t, "side"),
            pick(t, "outcome"),
            float(pick(t, "size") or 0),
            float(pick(t, "price") or 0),
            ts_str,
            minutes,
            pick(t, "proxy_wallet", "proxyWallet"),
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
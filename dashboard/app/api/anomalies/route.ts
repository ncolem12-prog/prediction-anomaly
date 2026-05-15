import { NextResponse } from 'next/server'
import Database from 'better-sqlite3'
import path from 'path'

// Points to your SQLite database one level up from the dashboard folder
const DB_PATH = path.join(process.cwd(), '..', 'data', 'anomaly.db')

export async function GET() {
  try {
    const db = new Database(DB_PATH, { readonly: true })

    // Summary stats for the header cards
    const stats = db.prepare(`
      SELECT
        COUNT(*)                                    as total_trades,
        SUM(is_anomaly)                             as total_flagged,
        ROUND(AVG(CASE WHEN is_anomaly=1 
              THEN size END), 2)                    as avg_flagged_size,
        ROUND(SUM(CASE WHEN is_anomaly=1 
              THEN size ELSE 0 END), 2)             as flagged_volume,
        ROUND(SUM(size), 2)                         as total_volume
      FROM trades
    `).get() as Record<string, number>

    // Breakdown by anomaly type
    const byType = db.prepare(`
      SELECT anomaly_type, COUNT(*) as count
      FROM trades
      WHERE is_anomaly = 1
      GROUP BY anomaly_type
      ORDER BY count DESC
    `).all()

    // Flag rate per market
    const byMarket = db.prepare(`
      SELECT
        m.question,
        COUNT(t.id)              as total_trades,
        SUM(t.is_anomaly)        as flagged,
        ROUND(100.0 * SUM(t.is_anomaly) / COUNT(t.id), 1) as flag_rate,
        ROUND(MAX(t.size), 2)    as max_bet
      FROM trades t
      JOIN markets m ON t.condition_id = m.condition_id
      GROUP BY m.question
      ORDER BY flag_rate DESC
    `).all()

    // Top 50 anomalies for the main table
    const anomalies = db.prepare(`
      SELECT
        t.id,
        t.side,
        t.outcome,
        t.size,
        t.price,
        t.timestamp,
        t.minutes_to_close,
        t.size_zscore,
        t.timing_zscore,
        t.anomaly_type,
        m.question
      FROM trades t
      JOIN markets m ON t.condition_id = m.condition_id
      WHERE t.is_anomaly = 1
      ORDER BY t.size_zscore DESC
      LIMIT 50
    `).all()

    db.close()

    return NextResponse.json({
      stats,
      byType,
      byMarket,
      anomalies,
      generated_at: new Date().toISOString()
    })

  } catch (error) {
    console.error('DB error:', error)
    return NextResponse.json(
      { error: 'Could not read database. Run fetch.py and detect.py first.' },
      { status: 500 }
    )
  }
}
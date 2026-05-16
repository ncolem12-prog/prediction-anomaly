"use client"

import { useEffect, useState } from "react"

// ── Types ────────────────────────────────────────────────────────
interface Stats {
  total_trades: number
  total_flagged: number
  avg_flagged_size: number
  flagged_volume: number
  total_volume: number
}

interface Anomaly {
  id: string
  question: string
  side: string
  outcome: string
  size: number
  price: number
  timestamp: string
  minutes_to_close: number
  size_zscore: number
  timing_zscore: number
  anomaly_type: string
}

interface MarketStat {
  question: string
  total_trades: number
  flagged: number
  flag_rate: number
  max_bet: number
}

interface TypeStat {
  anomaly_type: string
  count: number
}

// ── Helpers ──────────────────────────────────────────────────────
function fmt$(n: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", maximumFractionDigits: 0
  }).format(n)
}

function fmtZ(n: number) {
  return n?.toFixed(2) ?? "—"
}

function anomalyColor(type: string) {
  if (type === "confluence") return "bg-red-100 text-red-800 border border-red-200"
  if (type === "size")       return "bg-orange-100 text-orange-800 border border-orange-200"
  if (type === "timing")     return "bg-yellow-100 text-yellow-800 border border-yellow-200"
  return "bg-gray-100 text-gray-600"
}

function anomalyLabel(type: string) {
  if (type === "confluence") return "⚡ Confluence"
  if (type === "size")       return "📏 Size"
  if (type === "timing")     return "⏱ Timing"
  return type
}

// ── Main component ───────────────────────────────────────────────
export default function Dashboard() {
  const [stats, setStats]       = useState<Stats | null>(null)
  const [anomalies, setAnomalies] = useState<Anomaly[]>([])
  const [byMarket, setByMarket] = useState<MarketStat[]>([])
  const [byType, setByType]     = useState<TypeStat[]>([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState("")
  const [filter, setFilter]     = useState("all")

  useEffect(() => {
    fetch("/data.json")
      .then(r => r.json())
      .then(data => {
        if (data.error) { setError(data.error); return }
        setStats(data.stats)
        setAnomalies(data.anomalies)
        setByMarket(data.by_market || data.byMarket || [])
        setByType(data.by_type || data.byType || [])
      })
      .catch(() => setError("Could not connect to API."))
      .finally(() => setLoading(false))
  }, [])

  const filtered = filter === "all"
    ? anomalies
    : anomalies.filter(a => a.anomaly_type === filter)

  if (loading) return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <p className="text-gray-400 text-lg animate-pulse">Loading anomaly data...</p>
    </div>
  )

  if (error) return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <div className="text-center">
        <p className="text-red-400 text-lg mb-2">Error: {error}</p>
        <p className="text-gray-500 text-sm">Run fetch.py and detect.py first, then refresh.</p>
      </div>
    </div>
  )

  const flagRate = stats
    ? (stats.total_flagged / stats.total_trades * 100).toFixed(1)
    : "0"
  const volumePct = stats
    ? (stats.flagged_volume / stats.total_volume * 100).toFixed(1)
    : "0"

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-6">
      <div className="max-w-7xl mx-auto">

        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-1">
            Prediction Market Anomaly Detector
          </h1>
          <p className="text-gray-400 text-sm">
            Live Polymarket data · Z-score based detection · 
            Size, timing, and confluence signals
          </p>
        </div>

        {/* Stat cards */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
              <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">
                Total Trades
              </p>
              <p className="text-2xl font-bold text-white">
                {stats.total_trades.toLocaleString()}
              </p>
            </div>
            <div className="bg-red-950 rounded-xl p-4 border border-red-900">
              <p className="text-red-300 text-xs uppercase tracking-wide mb-1">
                Anomalies Flagged
              </p>
              <p className="text-2xl font-bold text-red-400">
                {stats.total_flagged} 
                <span className="text-sm font-normal ml-1">({flagRate}%)</span>
              </p>
            </div>
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
              <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">
                Avg Flagged Bet
              </p>
              <p className="text-2xl font-bold text-orange-400">
                {fmt$(stats.avg_flagged_size)}
              </p>
            </div>
            <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
              <p className="text-gray-400 text-xs uppercase tracking-wide mb-1">
                Flagged Volume Share
              </p>
              <p className="text-2xl font-bold text-yellow-400">
                {volumePct}%
              </p>
              <p className="text-gray-500 text-xs mt-1">
                of {fmt$(stats.total_volume)} total
              </p>
            </div>
          </div>
        )}

        {/* Middle row: type breakdown + market flag rates */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">

          {/* Anomaly type breakdown */}
          <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
            <h2 className="text-sm font-semibold text-gray-300 uppercase 
                           tracking-wide mb-4">
              Flag Type Breakdown
            </h2>
            {byType.map(t => (
              <div key={t.anomaly_type} className="flex items-center gap-3 mb-3">
                <span className={`text-xs px-2 py-1 rounded-full font-medium
                                  ${anomalyColor(t.anomaly_type)}`}>
                  {anomalyLabel(t.anomaly_type)}
                </span>
                <div className="flex-1 bg-gray-800 rounded-full h-2">
                  <div
                    className="bg-orange-500 h-2 rounded-full"
                    style={{
                      width: `${(t.count / (stats?.total_flagged || 1)) * 100}%`
                    }}
                  />
                </div>
                <span className="text-gray-300 text-sm font-mono w-8 text-right">
                  {t.count}
                </span>
              </div>
            ))}
            <p className="text-gray-600 text-xs mt-4 leading-relaxed">
              Confluence = large AND late. Rarest flag, highest signal strength.
            </p>
          </div>

          {/* Flag rate by market */}
          <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
            <h2 className="text-sm font-semibold text-gray-300 uppercase 
                           tracking-wide mb-4">
              Flag Rate by Market
            </h2>
            <div className="space-y-2 max-h-52 overflow-y-auto">
              {byMarket.map(m => (
                <div key={m.question}>
                  <div className="flex justify-between text-xs text-gray-400 mb-1">
                    <span className="truncate max-w-xs">{m.question}</span>
                    <span className="ml-2 font-mono text-gray-300 shrink-0">
                      {m.flag_rate}%
                    </span>
                  </div>
                  <div className="bg-gray-800 rounded-full h-1.5">
                    <div
                      className="bg-yellow-500 h-1.5 rounded-full"
                      style={{ width: `${Math.min(m.flag_rate * 10, 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Anomaly table */}
        <div className="bg-gray-900 rounded-xl border border-gray-800">
          <div className="p-5 border-b border-gray-800 flex items-center 
                          justify-between flex-wrap gap-3">
            <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wide">
              Top Flagged Trades
            </h2>
            {/* Filter buttons */}
            <div className="flex gap-2">
              {["all", "confluence", "size", "timing"].map(f => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`text-xs px-3 py-1 rounded-full border transition-colors
                    ${filter === f
                      ? "bg-orange-500 border-orange-500 text-white"
                      : "border-gray-700 text-gray-400 hover:border-gray-500"
                    }`}
                >
                  {f === "all" ? "All" : anomalyLabel(f)}
                </button>
              ))}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-gray-500 
                                text-xs uppercase tracking-wide">
                  <th className="text-left p-4">Market</th>
                  <th className="text-left p-4">Flag</th>
                  <th className="text-right p-4">Bet Size</th>
                  <th className="text-right p-4">Size Z</th>
                  <th className="text-right p-4">Timing Z</th>
                  <th className="text-right p-4">Min to Close</th>
                  <th className="text-left p-4">Side</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((a, i) => (
                  <tr
                    key={a.id}
                    className={`border-b border-gray-800/50 hover:bg-gray-800/40 
                                transition-colors
                                ${i % 2 === 0 ? "" : "bg-gray-900/50"}`}
                  >
                    <td className="p-4 max-w-xs">
                      <span className="text-gray-200 text-xs leading-snug 
                                       line-clamp-2">
                        {a.question}
                      </span>
                    </td>
                    <td className="p-4">
                      <span className={`text-xs px-2 py-1 rounded-full font-medium
                                        ${anomalyColor(a.anomaly_type)}`}>
                        {anomalyLabel(a.anomaly_type)}
                      </span>
                    </td>
                    <td className="p-4 text-right font-mono text-orange-300 
                                   font-semibold">
                      {fmt$(a.size)}
                    </td>
                    <td className="p-4 text-right font-mono text-gray-300">
                      {fmtZ(a.size_zscore)}
                    </td>
                    <td className="p-4 text-right font-mono text-gray-300">
                      {fmtZ(a.timing_zscore)}
                    </td>
                    <td className="p-4 text-right font-mono text-gray-400 text-xs">
                      {a.minutes_to_close < 60
                        ? `${Math.round(a.minutes_to_close)}m`
                        : `${Math.round(a.minutes_to_close / 60 / 24)}d`}
                    </td>
                    <td className="p-4">
                      <span className={`text-xs font-medium
                        ${a.side === "BUY" 
                          ? "text-green-400" 
                          : "text-red-400"}`}>
                        {a.side} {a.outcome}
                      </span>
                      <p className="text-gray-600 text-xs mt-0.5">
                        {a.side === "BUY"
                          ? `Betting ${a.outcome.toLowerCase()} will happen`
                          : `Exiting a ${a.outcome.toLowerCase()} position`}
                      </p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="p-4 border-t border-gray-800">
            <p className="text-gray-600 text-xs">
              Showing {filtered.length} flagged trades · 
              Z-scores computed per market · 
              Confluence = size z &gt; 1.5 AND timing z &gt; 1.5 simultaneously
            </p>
          </div>
        </div>

      </div>
    </div>
  )
}
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertCircle, Download, Loader2 } from 'lucide-react'
import PlayerSearchBase from '../shared/components/PlayerSearchBase'
import PredictionCard from '../features/predictions/PredictionCard'
import { STATS, searchPlayers, timeLabel, type Archive, type Forecast, type Game, type Quality } from './api'

export function Notice({ error }: { error: unknown }) {
  if (!error) return null
  return <div role="alert" className="card border-accent-danger/30 p-4 flex gap-3 text-sm text-accent-danger"><AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />{error instanceof Error ? error.message : String(error)}</div>
}

export function Loading({ children = 'Loading…' }: { children?: string }) {
  return <div role="status" className="flex items-center gap-3 py-6 text-sm text-text-secondary"><Loader2 className="w-4 h-4 animate-spin shrink-0" />{children}</div>
}

export function Search({ destination = '/forecasts' }: { destination?: string }) {
  const navigate = useNavigate()
  return <PlayerSearchBase searchPlayers={searchPlayers} placeholder="Search for a player (e.g., Nikola Jokic)" onSelect={p => navigate(`${destination}?team=${p.team_id}&player=${p.player_id}`)} />
}

export function ForecastResult({ result, games = [], saved = false }: { result: Forecast; games?: Game[]; saved?: boolean }) {
  return <section className="space-y-6" aria-label="Player forecast" aria-live="polite">
    <div><h2 className="heading-display text-3xl font-bold text-text-primary">{result.player_name}</h2><p className="text-sm text-text-secondary mt-1">{result.event.name} · {timeLabel(result.event.starts_at)}{saved ? ' · Saved forecast' : ''}</p></div>
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
      {STATS.map(stat => <PredictionCard key={`${result.as_of}-${stat}`} stat={stat} intervalLevel={result.predictions[stat].interval_level} prediction={{ stat, ...result.predictions[stat], confidence: 0, recent_avg: games.length ? games.slice(0, 10).reduce((sum, g) => sum + g[stat], 0) / Math.min(games.length, 10) : undefined }} />)}
    </div>
    {result.offers.map((offer, i) => <div key={i} className="card card-accent p-5 space-y-3">
      <h3 className="heading-display text-xl font-semibold">{offer.stat} {offer.side} {offer.line} · {offer.book}</h3>
      <div className="flex flex-wrap gap-6 font-mono text-sm"><span>Win {(offer.prob_win * 100).toFixed(1)}%</span><span>Loss {(offer.prob_loss * 100).toFixed(1)}%</span><span>Push {(offer.prob_push * 100).toFixed(1)}%</span></div>
      <p className="text-sm text-text-secondary">Estimated net return per dollar risked: <span className="font-mono text-accent">{(offer.expected_profit_per_unit_risked * 100).toFixed(1)}%</span></p>
      <p className="text-xs text-text-muted">{offer.reasons.join('. ')}.</p>
    </div>)}
    <div className="card p-5 text-xs text-text-secondary leading-relaxed space-y-2">
      {saved && <p className="text-accent-warning">Snapshot from {timeLabel(result.as_of)}. Generate a new forecast to use a current price.</p>}
      <p>History through {result.history_through} · Model calibrated through {result.model.calibrated_through}. Ranges cover 80% of modeled outcomes, conditional on participation.</p>
      {result.notes.map(note => <p key={note}>{note}</p>)}
      {result.data_quality.quarantined_games?.map(g => <p key={g.event_id}>Excluded game {g.event_id} ({new Date(g.date).toLocaleDateString()}): {g.reason}</p>)}
    </div>
  </section>
}

export function VerifiedGames({ games, quality }: { games: Game[]; quality: Quality }) {
  const [all, setAll] = useState(false)
  return <section className="space-y-4">
    <div className="flex justify-between items-center"><h2 className="heading-display text-2xl font-semibold">Recent Game Log</h2><button type="button" className="text-xs text-accent" onClick={() => setAll(!all)}>{all ? 'Recent 10' : `All ${games.length}`}</button></div>
    <div className="card overflow-hidden"><div className="overflow-x-auto"><table className="w-full text-sm text-right whitespace-nowrap"><thead className="bg-bg-secondary text-text-muted text-[11px] uppercase tracking-wider"><tr>{['Date', 'Team', 'MIN', ...STATS].map(c => <th key={c} className="px-4 py-3 first:text-left font-medium">{c}</th>)}</tr></thead><tbody>{(all ? games : games.slice(0, 10)).map(g => <tr key={g.GAME_ID} className="border-t border-border-subtle hover:bg-bg-elevated/30"><td className="px-4 py-3 text-left text-text-secondary">{g.GAME_DATE}</td><td className="px-4 py-3 text-text-muted">{g.TEAM}</td><td className="px-4 py-3 font-mono">{g.MIN.toFixed(1)}</td>{STATS.map(s => <td key={s} className={`px-4 py-3 font-mono ${s === 'PRA' ? 'text-accent' : ''}`}>{g[s]}</td>)}</tr>)}</tbody></table></div></div>
    <div className="text-xs text-text-muted leading-relaxed space-y-1"><p>{quality.verified_games} appearances checked against final ESPN box scores · {quality.corrections_this_refresh} corrections this refresh · {quality.excluded_zero_minute_rows} rounded-zero-minute rows excluded.</p><p>Source cache: {timeLabel(quality.oldest_fetch * 1000)}–{timeLabel(quality.newest_fetch * 1000)}.</p>{quality.quarantined_games?.map(g => <p key={g.event_id} className="text-accent-warning">Excluded {new Date(g.date).toLocaleDateString()} (game {g.event_id}): {g.reason}</p>)}{!!quality.excluded_non_regular_games?.length && <p>{quality.excluded_non_regular_games.length} play-in or other non-regular-season games excluded.</p>}</div>
  </section>
}

export function SavedList({ data, limit = 30, onSelect }: { data?: Archive; limit?: number; onSelect?: (f: Forecast) => void }) {
  if (!data?.forecasts.length) return <div className="card p-8 text-center text-sm text-text-secondary">No saved forecasts yet. <Link to="/forecasts" className="text-accent">Analyze a player</Link> to get started.</div>
  return <div className="grid gap-4 sm:grid-cols-2">{data.forecasts.slice(0, limit).map(item => <button type="button" key={item.id} onClick={() => onSelect?.(item.forecast)} className="card card-hover p-5 text-left"><div className="flex justify-between gap-3 items-center"><h3 className="heading-display text-xl font-semibold">{item.forecast.player_name}</h3><span className="badge badge-neutral">Research</span></div><p className="text-xs text-text-secondary mt-2">{item.forecast.event.team} {item.forecast.event.home ? 'vs' : '@'} {item.forecast.event.opponent} · {item.forecast.game_date}</p><div className="flex gap-4 flex-wrap mt-4">{STATS.map(s => <span key={s} className="text-xs text-text-muted">{s} <span className="font-mono text-text-primary">{item.forecast.predictions[s].prediction.toFixed(1)}</span></span>)}</div><p className="text-[10px] text-text-muted mt-3">Saved {timeLabel(item.forecast.as_of)}</p></button>)}</div>
}

export function Export({ data }: { data?: Archive }) {
  return <button className="btn btn-secondary text-sm" disabled={!data} onClick={() => { const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })); const link = document.createElement('a'); link.href = url; link.download = 'nba-eval-personal-history.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000) }}><Download className="w-4 h-4" />Export</button>
}

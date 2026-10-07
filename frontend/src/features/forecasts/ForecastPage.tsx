import { useState, type FormEvent } from 'react'
import { AlertCircle, Loader2 } from 'lucide-react'
import PlayerSearch from '../../shared/components/PlayerSearch'
import { apiFetch, API_BASE } from '../../api/client'
import type { PlayerInfo } from '../../api/types'

type Stat = 'PTS' | 'REB' | 'AST' | 'PRA'
type Forecast = {
  player_name: string
  game_date: string
  history_through: string
  model: { trained_through: string; calibrated_through: string }
  predictions: Record<Stat, { prediction: number; range_low: number; range_high: number }>
  offers: Array<{
    stat: Stat; side: string; line: number; book: string
    prob_win: number; prob_loss: number; prob_push: number
    expected_profit_per_unit_risked: number; reasons: string[]
  }>
  notes: string[]
}

const inputClass = 'w-full rounded-lg border border-border-subtle bg-bg-elevated px-3 py-2 text-text-primary'
const stats: Stat[] = ['PTS', 'REB', 'AST', 'PRA']

export default function ForecastPage() {
  const [player, setPlayer] = useState<PlayerInfo | null>(null)
  const [team, setTeam] = useState('')
  const [opponent, setOpponent] = useState('')
  const [tipoff, setTipoff] = useState('')
  const [home, setHome] = useState(true)
  const [availability, setAvailability] = useState('unknown')
  const [hasOffer, setHasOffer] = useState(false)
  const [stat, setStat] = useState<Stat>('PTS')
  const [side, setSide] = useState('OVER')
  const [line, setLine] = useState('')
  const [odds, setOdds] = useState('')
  const [book, setBook] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<Forecast | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!player || pending) return
    setError('')
    setResult(null)
    const start = new Date(tipoff)
    if (!Number.isFinite(start.getTime()) || start.getTime() <= Date.now()) {
      setError('Choose a future tipoff time.')
      return
    }
    const american = Number(odds)
    if (hasOffer && (!Number.isFinite(american) || Math.abs(american) < 100)) {
      setError('Enter American odds of -100 or lower, or +100 or higher.')
      return
    }
    const eventId = `manual:${start.toISOString()}:${team}:${opponent}:${home ? 'home' : 'away'}`
    const offers = hasOffer ? [{
      event_id: eventId, player_id: String(player.player_id), stat, side,
      line: Number(line), decimal_odds: 1 + (american > 0 ? american / 100 : 100 / Math.abs(american)),
      book, captured_at: new Date().toISOString(), starts_at: start.toISOString(),
    }] : []
    setPending(true)
    try {
      const response = await apiFetch(`${API_BASE}/forecasts/player`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player_name: player.player_name, event_id: eventId,
          starts_at: start.toISOString(), team, home, availability, offers }),
      })
      const body = await response.json()
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Check the event and offer details, then try again.')
      setResult(body as Forecast)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Forecast unavailable.')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 py-6">
      <div>
        <h1 className="font-display text-3xl font-bold text-text-primary">Player forecasts</h1>
        <p className="mt-2 text-sm text-text-secondary">Forecast points, rebounds, assists and PRA with a model trained across the league. Enter the upcoming matchup and, optionally, a price you can currently see at your sportsbook.</p>
      </div>
      <form onSubmit={submit} onChange={() => setResult(null)} className="space-y-5 rounded-xl border border-border-subtle bg-bg-secondary p-5">
        <fieldset disabled={pending} className="space-y-5 disabled:opacity-60">
          <PlayerSearch placeholder="Select a player…" onSelect={selected => {
            setPlayer(selected); setTeam(selected.team_abbrev || ''); setResult(null)
          }} />
          {player && <p className="text-sm font-semibold text-accent">Forecasting {player.player_name}</p>}
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-1 text-sm text-text-secondary">Current team
              <input className={inputClass} value={team} onChange={e => setTeam(e.target.value.toUpperCase())} placeholder="BOS" pattern="[A-Z]{2,3}" maxLength={3} required />
            </label>
            <label className="space-y-1 text-sm text-text-secondary">Opponent
              <input className={inputClass} value={opponent} onChange={e => setOpponent(e.target.value.toUpperCase())} placeholder="NYK" pattern="[A-Z]{2,3}" maxLength={3} required />
            </label>
            <label className="space-y-1 text-sm text-text-secondary">Tipoff (your local time)
              <input className={inputClass} type="datetime-local" value={tipoff} onChange={e => setTipoff(e.target.value)} required />
            </label>
            <label className="space-y-1 text-sm text-text-secondary">Player availability
              <select className={inputClass} value={availability} onChange={e => setAvailability(e.target.value)}>
                <option value="unknown">Not confirmed</option><option value="available">Available</option>
                <option value="questionable">Questionable</option><option value="out">Out</option>
              </select>
            </label>
          </div>
          <label className="flex items-center gap-2 text-sm text-text-secondary"><input type="checkbox" checked={home} onChange={e => setHome(e.target.checked)} />Player's team is at home</label>
          <label className="flex items-center gap-2 text-sm text-text-secondary"><input type="checkbox" checked={hasOffer} onChange={e => setHasOffer(e.target.checked)} />Evaluate a current sportsbook offer</label>
          {hasOffer && <div className="grid gap-3 sm:grid-cols-3">
            <label className="text-sm text-text-secondary">Stat<select className={inputClass} value={stat} onChange={e => setStat(e.target.value as Stat)}>{stats.map(s => <option key={s}>{s}</option>)}</select></label>
            <label className="text-sm text-text-secondary">Side<select className={inputClass} value={side} onChange={e => setSide(e.target.value)}><option>OVER</option><option>UNDER</option></select></label>
            <label className="text-sm text-text-secondary">Line<input className={inputClass} type="number" min="0" step="0.5" value={line} onChange={e => setLine(e.target.value)} required /></label>
            <label className="text-sm text-text-secondary">American odds<input className={inputClass} type="number" step="1" value={odds} onChange={e => setOdds(e.target.value)} placeholder="-110" required /></label>
            <label className="text-sm text-text-secondary sm:col-span-2">Sportsbook<input className={inputClass} value={book} onChange={e => setBook(e.target.value)} maxLength={100} required /></label>
            <p className="text-xs text-text-muted sm:col-span-3">Confirm this offer is available now. The quote is recorded at submission time.</p>
          </div>}
          <button type="submit" disabled={!player || pending} className="flex items-center gap-2 rounded-lg bg-accent px-5 py-2.5 font-semibold text-bg-primary disabled:opacity-50">
            {pending && <Loader2 className="h-4 w-4 animate-spin" />}{pending ? 'Forecasting…' : 'Run forecast'}
          </button>
        </fieldset>
      </form>
      {error && <p role="alert" className="flex items-center gap-2 text-sm text-red-400"><AlertCircle className="h-4 w-4" />{error}</p>}
      {result && <section aria-live="polite" className="space-y-4">
        <h2 className="font-display text-xl text-text-primary">{result.player_name} · {result.game_date}</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {stats.map(s => <div key={s} className="rounded-xl border border-border-subtle bg-bg-secondary p-4">
            <p className="text-sm text-text-muted">{s}</p><p className="mt-1 text-3xl font-semibold text-text-primary">{result.predictions[s].prediction.toFixed(1)}</p>
            <p className="mt-2 text-xs text-text-secondary">80% model range: {result.predictions[s].range_low}–{result.predictions[s].range_high}</p>
          </div>)}
        </div>
        {result.offers.map((quote, i) => <div key={i} className="space-y-2 rounded-xl border border-border-subtle bg-bg-secondary p-4">
          <h3 className="font-semibold text-text-primary">{quote.book} · {quote.stat} {quote.side} {quote.line}</h3>
          <p className="text-sm text-text-secondary">Win {(quote.prob_win * 100).toFixed(1)}% · Loss {(quote.prob_loss * 100).toFixed(1)}% · Push {(quote.prob_push * 100).toFixed(1)}%</p>
          <p className="text-sm text-text-primary">Estimated net return per unit risked: {(quote.expected_profit_per_unit_risked * 100).toFixed(1)}%</p>
          <p className="text-xs text-text-muted">{quote.reasons.join('. ')}.</p>
        </div>)}
        <p className="text-xs text-text-muted">Player history through {result.history_through}. Model fitted through {result.model.trained_through}; uncertainty calibrated through {result.model.calibrated_through}.</p>
        <ul className="list-disc space-y-1 pl-5 text-xs text-text-muted">{result.notes.map(note => <li key={note}>{note}</li>)}</ul>
      </section>}
    </div>
  )
}

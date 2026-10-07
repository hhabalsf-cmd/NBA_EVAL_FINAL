import { useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { Loader2, Zap } from 'lucide-react'
import { api, archiveQuery, statusQuery, teamQuery, STATS, timeLabel, type Forecast, type Game, type Player, type Matchup, type Quality } from './api'
import { ForecastResult, Loading, Notice, Search, VerifiedGames } from './components'

export default function Workspace({ research = false }: { research?: boolean }) {
  const [params, setParams] = useSearchParams()
  const team = params.get('team') || '13', playerId = params.get('player') || ''
  const teams = useQuery(teamQuery)
  const roster = useQuery({ queryKey: ['personal-roster', team], queryFn: ({ signal }) => api<{ players: Player[] }>(`/teams/${team}/roster`, { signal }) })
  const schedule = useQuery({ queryKey: ['personal-schedule', team], queryFn: ({ signal }) => api<{ events: Matchup[] }>(`/teams/${team}/schedule`, { signal }) })
  const history = useQuery({ queryKey: ['personal-player-history', playerId], queryFn: ({ signal }) => api<{ games: Game[]; quality: Quality }>(`/players/${playerId}/history`, { signal }), enabled: !!playerId })
  const status = useQuery(statusQuery)
  const [availability, setAvailability] = useState('unknown'), [hasOffer, setHasOffer] = useState(false)
  const [pending, setPending] = useState(false), [error, setError] = useState<unknown>(null)
  const [result, setResult] = useState<Forecast | null>(null)
  const client = useQueryClient()
  const player = roster.data?.players.find(p => p.id === playerId)
  const eventId = params.get('event') || schedule.data?.events[0]?.id || ''
  const event = schedule.data?.events.find(g => g.id === eventId)
  const sourceOut = !!player?.injuries.some(i => ['out', 'suspension', 'suspended'].includes((i.status || '').toLowerCase()))
  const automatic = useQuery({
    queryKey: ['personal-auto-forecast', team, playerId, eventId],
    enabled: !research && !!player && !!event && !!history.data && !history.isFetching && !!status.data?.model && !sourceOut,
    retry: false,
    refetchOnMount: false,
    queryFn: async () => {
      // Let an in-flight POST finish so remounting cannot save duplicate forecasts.
      const forecast = await api<Forecast>('/forecast', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ team_id: team, player_id: playerId, event_id: eventId, availability: 'unknown' }),
      })
      await client.invalidateQueries({ queryKey: archiveQuery.queryKey })
      return forecast
    },
  })
  const displayedResult = result || automatic.data
  const busy = pending || automatic.isFetching
  function select(values: Record<string, string>) { setResult(null); setError(null); setParams(values) }
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (pending || !history.data || !player) return
    const form = new FormData(e.currentTarget)
    const body: Record<string, unknown> = { team_id: team, player_id: playerId, event_id: eventId, availability }
    if (hasOffer) {
      const odds = Number(form.get('odds'))
      if (Math.abs(odds) < 100 || !String(form.get('book')).trim()) { setError('Enter American odds of +100 or higher, or -100 or lower, and a sportsbook.'); return }
      body.quote = { stat: form.get('stat'), side: form.get('side'), line: Number(form.get('line')), american_odds: odds, book: String(form.get('book')).trim() }
    }
    setPending(true); setError(null); setResult(null)
    try {
      const forecast = await api<Forecast>('/forecast', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      setResult(forecast)
      await client.invalidateQueries({ queryKey: archiveQuery.queryKey })
    } catch (failure) { setError(failure) }
    finally { setPending(false) }
  }
  const pageError = error || automatic.error || teams.error || roster.error || schedule.error || history.error || status.error || status.data?.model_error
  return <div className="space-y-8">
    <div><h1 className="heading-display text-3xl sm:text-4xl font-bold mb-2">{research ? 'Player Research' : 'Player Forecasts'}</h1><p className="text-sm text-text-secondary">{research ? 'Verified game logs and recent form, using free ESPN data.' : 'Select a player. We find their next game, check ESPN availability, and automatically predict points, rebounds, assists, and combined stats.'}</p></div>
    <Search destination={research ? '/research' : '/forecasts'} />
    <Notice error={pageError} />
    {!research && player && <section className="card card-accent p-5 space-y-2" aria-label="Next game and availability">
      <h2 className="heading-display text-2xl font-semibold">{player.name}</h2>
      <p className="text-sm text-text-secondary">{event ? `${params.get('event') ? 'Selected game' : 'Next game'}: ${event.name} · ${timeLabel(event.starts_at)}` : schedule.isPending ? 'Finding the next game…' : 'No upcoming supported regular-season game is listed yet.'}</p>
      <p className={`text-sm ${sourceOut ? 'text-accent-danger' : 'text-text-secondary'}`}>ESPN availability: {player.injuries.length ? player.injuries.map(i => i.status || 'Unclear').join(', ') : 'No injury listed · participation not confirmed'}.</p>
      {sourceOut && <p role="status" className="text-sm text-accent-danger">ESPN lists this player as out or suspended. An active-player prediction will not be generated.</p>}
    </section>}
    {history.isFetching && <Loading>Checking final box scores. The first visit can take 30–90 seconds; subsequent visits use your local cache.</Loading>}
    {busy && <Loading>Generating and saving your forecast automatically…</Loading>}
    {!research && displayedResult && !sourceOut && <ForecastResult result={displayedResult} games={history.data?.games} />}
    <form onSubmit={submit} onChange={() => setResult(null)} className="card p-5 sm:p-6">
      <fieldset disabled={busy} className="space-y-5 disabled:opacity-60">
        {!research && <p className="text-xs text-text-muted">The next-game prediction runs automatically. Use these options to change the matchup or compare a sportsbook price.</p>}
        <div className="grid sm:grid-cols-2 gap-4">
          <label className="text-xs text-text-secondary space-y-2"><span className="label-xs">Team</span><select className="input w-full" aria-label="Team" value={team} onChange={e => { setAvailability('unknown'); select({ team: e.target.value }) }}>{teams.data?.teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label>
          <label className="text-xs text-text-secondary space-y-2"><span className="label-xs">Player</span><select className="input w-full" aria-label="Player" required value={playerId} onChange={e => { setAvailability('unknown'); select({ team, player: e.target.value, ...(params.get('event') ? { event: eventId } : {}) }) }}><option value="">{roster.isPending ? 'Loading roster…' : 'Select a player'}</option>{roster.data?.players.map(p => <option key={p.id} value={p.id}>{p.name} · {p.position}</option>)}</select></label>
          {!research && <><label className="text-xs text-text-secondary space-y-2"><span className="label-xs">Upcoming game</span><select className="input w-full" aria-label="Upcoming game" required value={eventId} onChange={e => select({ team, player: playerId, event: e.target.value })}>{!schedule.data?.events.length && <option value="">{schedule.isPending ? 'Loading schedule…' : 'No upcoming regular-season games'}</option>}{schedule.data?.events.map(g => <option key={g.id} value={g.id}>{g.home ? 'vs' : '@'} {g.opponent} · {timeLabel(g.starts_at)}</option>)}</select></label><label className="text-xs text-text-secondary space-y-2"><span className="label-xs">Participation check</span><select className="input w-full" aria-label="Participation check" value={availability} onChange={e => setAvailability(e.target.value)}><option value="unknown">Not confirmed yet</option><option value="available">I confirmed they are expected to play</option><option value="questionable">Questionable / uncertain</option><option value="out">Out</option></select></label></>}
        </div>
        {player && <p className="text-xs text-text-muted">{player.injuries.length ? `ESPN injury listing: ${player.injuries.map(i => i.status || 'Unclear').join(', ')}. Check near tipoff.` : 'No injury entry returned. This does not confirm participation.'}</p>}
        {!research && <><label className="flex gap-2 items-center text-sm text-text-secondary"><input type="checkbox" checked={hasOffer} onChange={e => setHasOffer(e.target.checked)} />Compare a sportsbook price</label>
          {hasOffer && <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 border-t border-border-subtle pt-5">
            <label className="text-xs text-text-secondary">Stat<select name="stat" className="input w-full mt-2">{STATS.map(s => <option key={s}>{s}</option>)}</select></label>
            <label className="text-xs text-text-secondary">Side<select name="side" className="input w-full mt-2"><option>OVER</option><option>UNDER</option></select></label>
            <label className="text-xs text-text-secondary">Line<input name="line" type="number" min="0" max="300" step="0.5" required placeholder="24.5" className="input w-full mt-2" /></label>
            <label className="text-xs text-text-secondary">American odds<input name="odds" type="number" min="-100000" max="100000" step="1" required placeholder="-110" className="input w-full mt-2" /></label>
            <label className="text-xs text-text-secondary col-span-2">Sportsbook<input name="book" type="text" required maxLength={80} placeholder="Enter a price you can see now" className="input w-full mt-2" /></label>
          </div>}
          <button className="btn btn-primary" type="submit" disabled={busy || sourceOut || !player || !eventId || !history.data || history.isFetching || !status.data?.model}>{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}{busy ? 'Analyzing…' : hasOffer ? 'Compare Price' : 'Refresh Forecast'}</button>
        </>}
      </fieldset>
    </form>
    {history.data && <VerifiedGames games={history.data.games} quality={history.data.quality} />}
    <p className="text-xs text-text-muted">Forecasts are conditional on participation. No profitable betting edge has been validated. Model calibration: {status.data?.model?.calibrated_through || 'unavailable'}.</p>
  </div>
}

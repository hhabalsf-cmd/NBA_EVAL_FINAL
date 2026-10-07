import { useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate, Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { Home, Gamepad2, FlaskConical, ChartNoAxesCombined, ClipboardList, Trophy, Settings, ArrowRight, Search as SearchIcon, BarChart3, Target, Moon, Sun } from 'lucide-react'
import AppShell from '../shared/components/AppShell'
import { useThemeStore } from '../shared/store/themeStore'
import { homeHeroCopy } from '../features/home/copy'
import Workspace from './Workspace'
import { api, archiveQuery, statusQuery, teamQuery, STATS, timeLabel, type Forecast, type Matchup, type Stat } from './api'
import { Export, ForecastResult, Loading, Notice, SavedList, Search } from './components'

const navItems = [
  { to: '/app', icon: Home, label: 'Home' },
  { to: '/games', icon: Gamepad2, label: 'Games' },
  { to: '/research', icon: FlaskConical, label: 'Research' },
  { to: '/forecasts', icon: ChartNoAxesCombined, label: 'Forecasts' },
  { to: '/picks', icon: ClipboardList, label: 'Picks' },
  { to: '/leaderboard', icon: Trophy, label: 'Leaders' },
]

function PersonalMenu() {
  const [open, setOpen] = useState(false)
  return <div className="relative"><button aria-label="User menu" aria-expanded={open} className="w-8 h-8 rounded-full overflow-hidden hover:ring-2 hover:ring-accent/40 transition-all" onClick={() => setOpen(!open)}><span className="w-full h-full bg-accent/15 text-accent text-sm font-semibold flex items-center justify-center">P</span></button>{open && <div className="absolute right-0 mt-2 w-56 bg-bg-tertiary border border-border-subtle rounded-xl shadow-xl shadow-black/30 overflow-hidden animate-slide-up z-50"><div className="p-4 border-b border-border-subtle"><div className="text-sm font-medium">Personal workspace</div><div className="text-xs text-text-muted mt-1">Stored on this computer</div></div><Link to="/settings" onClick={() => setOpen(false)} className="px-4 py-3 text-sm text-text-secondary flex items-center gap-2.5 hover:bg-bg-elevated"><Settings className="w-3.5 h-3.5" />Settings</Link></div>}</div>
}

function PersonalHome() {
  const { data, error } = useQuery(archiveQuery)
  const status = useQuery(statusQuery)
  const navigate = useNavigate()
  const hero = homeHeroCopy(true)
  const latest = data?.forecasts[0]?.forecast
  const steps = [
    { icon: SearchIcon, title: 'Search Player', desc: 'Find a player on a current ESPN roster and choose their upcoming game.' },
    { icon: BarChart3, title: 'ML Prediction', desc: 'Verified final box scores feed the rebuilt model and its outcome ranges.' },
    { icon: Target, title: 'Evaluate Lines', desc: 'Compare a current price and save the research forecast on your computer.' },
  ]
  return <motion.div className="space-y-12" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
    <section className="pt-6 pb-2"><h1 className="heading-display text-4xl md:text-5xl font-bold text-text-primary mb-3">{hero.heading}</h1><p className="text-text-secondary mb-8 max-w-lg text-[15px] leading-relaxed">{hero.subheading}</p><Search /><p className="text-xs text-text-muted mt-3">Free ESPN data · Personal workspace · Initial roster search may take a few seconds</p></section>
    <Notice error={error || status.error || status.data?.model_error} />
    <section className="card p-5"><div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-5"><div className="flex flex-wrap items-center gap-6"><div><div className="label-xs mb-1">Data source</div><div className="font-mono text-xl font-semibold text-accent">ESPN</div></div><div className="h-8 w-px bg-border-subtle hidden sm:block" /><div><div className="label-xs mb-1">Saved forecasts</div><div className="font-mono text-xl font-semibold">{data?.forecasts.length === 30 ? '30+' : data?.forecasts.length ?? '—'}</div></div><div className="h-8 w-px bg-border-subtle hidden sm:block" /><div><div className="label-xs mb-1">Model</div><div className="font-mono text-xl font-semibold text-accent-success">{status.data?.model ? 'Ready' : 'Checking'}</div></div></div><Link to="/picks" className="btn btn-secondary text-sm">View History<ArrowRight className="w-3.5 h-3.5" /></Link></div></section>
    <section><div className="flex justify-between items-center mb-4"><h2 className="heading-display text-2xl font-semibold">Latest Player Forecast</h2><Link to="/forecasts" className="text-xs text-accent">Analyze a player →</Link></div>{latest ? <><p className="text-sm text-text-secondary mb-4">{latest.player_name} · {latest.game_date} · Saved research preview</p><div className="grid grid-cols-2 sm:grid-cols-4 gap-4">{STATS.map(stat => <div key={stat} className="card card-accent p-5 text-center"><div className="label-xs mb-2">{stat}</div><div className="font-mono text-2xl font-bold">{latest.predictions[stat].prediction.toFixed(1)}</div><div className="text-xs text-text-secondary mt-1">{latest.predictions[stat].range_low}–{latest.predictions[stat].range_high} · 80% range</div></div>)}</div></> : <div className="card p-8 text-center text-sm text-text-secondary">Search a player to generate your first forecast.</div>}</section>
    <section><h2 className="heading-display text-2xl font-semibold mb-4">Recent Analysis</h2><SavedList data={data} limit={4} onSelect={f => navigate('/picks?saved=' + encodeURIComponent(f.as_of))} /></section>
    <section className="card p-8"><h2 className="heading-display text-2xl font-semibold mb-8">How It Works</h2><div className="grid grid-cols-1 md:grid-cols-3 gap-8">{steps.map(({ icon: Icon, title, desc }) => <div key={title} className="flex gap-4"><div className="flex-shrink-0 w-9 h-9 rounded-lg bg-accent/10 flex items-center justify-center card-3d"><Icon className="w-4 h-4 text-accent" /></div><div><h3 className="font-medium text-text-primary text-sm mb-1">{title}</h3><p className="text-xs text-text-secondary leading-relaxed">{desc}</p></div></div>)}</div></section>
    <p className="text-xs text-text-muted">No profitable betting edge has been validated. Enter sportsbook prices manually and refresh near tipoff.</p>
  </motion.div>
}

function Games() {
  const [team, setTeam] = useState('13')
  const teams = useQuery(teamQuery)
  const games = useQuery({ queryKey: ['personal-schedule', team], queryFn: ({ signal }) => api<{ events: Matchup[] }>(`/teams/${team}/schedule`, { signal }) })
  return <div className="space-y-6"><div><h1 className="heading-display text-3xl sm:text-4xl font-bold mb-2">NBA Games</h1><p className="text-sm text-text-secondary">Upcoming regular-season matchups from ESPN. Tipoff times are local.</p></div><label className="block text-xs text-text-secondary">Team<select className="input w-full sm:max-w-xs mt-2" value={team} onChange={e => setTeam(e.target.value)}>{teams.data?.teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label><Notice error={teams.error || games.error} />{games.isPending ? <Loading /> : !games.data?.events.length ? <div className="card p-8 text-center text-sm text-text-secondary">No supported upcoming games are available yet.</div> : <div className="grid sm:grid-cols-2 gap-4">{games.data.events.map(g => <div key={g.id} className="card card-hover p-5"><div className="flex justify-between gap-3 text-xs text-text-muted"><span>{timeLabel(g.starts_at)}</span><span>Scheduled</span></div><h2 className="heading-display text-2xl font-semibold my-5">{g.home ? g.opponent : g.team}<span className="text-text-muted text-base mx-3">@</span>{g.home ? g.team : g.opponent}</h2><Link className="btn btn-secondary text-sm w-full" to={`/forecasts?team=${team}&event=${g.id}`}>Analyze Player Props<ArrowRight className="w-4 h-4" /></Link></div>)}</div>}</div>
}

function Picks() {
  const { data, error, isPending } = useQuery(archiveQuery)
  const [params, setParams] = useSearchParams()
  const selected = data?.forecasts.find(f => f.forecast.as_of === params.get('saved'))?.forecast
  return <div className="space-y-6"><div className="flex items-center justify-between gap-3"><h1 className="heading-display text-3xl sm:text-4xl font-bold">My Picks & Analysis</h1><Export data={data} /></div><p className="text-sm text-text-secondary">Your saved research forecasts. These are not placed or graded bets, so no betting win rate or ROI is reported.</p><Notice error={error} />{selected && <ForecastResult result={selected} saved />}{isPending ? <Loading /> : <SavedList data={data} onSelect={f => setParams({ saved: f.as_of })} />}<details className="card p-5"><summary className="heading-display text-xl cursor-pointer">Stat Corrections · {data?.corrections.length ?? 0}</summary><div className="space-y-3 mt-4">{data?.corrections.length ? data.corrections.map((c, i) => <div key={i} className="text-xs text-text-secondary border-t border-border-subtle pt-3 break-words"><p>{String(c.after.GAME_DATE)} · {c.key}</p><p>{['MIN', ...STATS].filter(s => c.before[s] !== c.after[s]).map(s => `${s}: ${c.before[s]} → ${c.after[s]}`).join(' · ')}</p></div>) : <p className="text-xs text-text-muted">No corrections observed in the histories checked so far. Excluded games appear in each forecast’s data notes.</p>}</div></details></div>
}

function Leaders() {
  const { data, error } = useQuery(archiveQuery)
  const [stat, setStat] = useState<Stat>('PTS')
  const latest = new Map<string, Forecast>()
  for (const item of data?.forecasts ?? []) if (!latest.has(item.forecast.player_id)) latest.set(item.forecast.player_id, item.forecast)
  const ranked = [...latest.values()].sort((a, b) => b.predictions[stat].prediction - a.predictions[stat].prediction)
  return <div className="space-y-6"><h1 className="heading-display text-3xl sm:text-4xl font-bold">Player Leaders</h1><p className="text-sm text-text-secondary">Players from your most recent saved analyses, ranked by projected {stat.toLowerCase()}. Games may differ; this is not a betting-performance leaderboard.</p><div className="flex gap-2">{STATS.map(s => <button key={s} className={`btn ${stat === s ? 'btn-primary' : 'btn-secondary'} text-sm`} onClick={() => setStat(s)}>{s}</button>)}</div><Notice error={error} /><div className="card divide-y divide-border-subtle">{ranked.length ? ranked.map((f, index) => <Link key={f.player_id} to={'/picks?saved=' + encodeURIComponent(f.as_of)} className="flex items-center gap-4 p-5 hover:bg-bg-elevated/30"><span className="font-mono text-text-muted w-6">{index + 1}</span><div className="flex-1"><h2 className="font-semibold text-sm">{f.player_name}</h2><p className="text-xs text-text-muted mt-1">{f.event.team} · {f.game_date}</p></div><span className="font-mono text-xl text-accent">{f.predictions[stat].prediction.toFixed(1)}</span></Link>) : <p className="p-8 text-sm text-text-secondary text-center">Save a player forecast to see it here.</p>}</div></div>
}

function PersonalSettings() {
  const { theme, toggleTheme } = useThemeStore()
  const status = useQuery(statusQuery)
  return <div className="space-y-6"><h1 className="heading-display text-3xl sm:text-4xl font-bold">Settings</h1><section className="card p-6 flex justify-between items-center"><div><h2 className="font-semibold text-sm">Appearance</h2><p className="text-xs text-text-secondary mt-1">Your original Bettin’ Jrys theme</p></div><button className="btn btn-secondary" onClick={toggleTheme}>{theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}{theme === 'dark' ? 'Light mode' : 'Dark mode'}</button></section><section className="card p-6 space-y-3 text-sm text-text-secondary"><h2 className="heading-display text-xl text-text-primary">Personal Workspace</h2><p>Free ESPN data. No paid keys or account required.</p><p>Saved forecasts and stat corrections stay in the local database on this computer.</p><p>Model calibrated through {status.data?.model?.calibrated_through || 'unavailable'}.</p><p className="text-xs text-text-muted">Use Start NBA Eval.cmd to open this app again. This local server accepts connections only from this computer.</p></section></div>
}

function Pages() {
  const location = useLocation()
  return <AnimatePresence mode="wait" initial={false}><motion.div key={location.pathname + location.search} initial={{ opacity: 0, y: 12, rotateX: 2 }} animate={{ opacity: 1, y: 0, rotateX: 0 }} exit={{ opacity: 0, y: -8, rotateX: -1 }} transition={{ duration: .25, ease: 'easeOut' }} style={{ perspective: 1200 }}><Routes location={location}><Route path="/" element={<Navigate to="/app" replace />} /><Route path="/app" element={<PersonalHome />} /><Route path="/forecasts" element={<Workspace />} /><Route path="/research" element={<Workspace research />} /><Route path="/games" element={<Games />} /><Route path="/picks" element={<Picks />} /><Route path="/leaderboard" element={<Leaders />} /><Route path="/settings" element={<PersonalSettings />} /><Route path="*" element={<Navigate to="/app" replace />} /></Routes></motion.div></AnimatePresence>
}

export default function PersonalApp() {
  return <BrowserRouter><AppShell navItems={navItems} isAuthenticated userMenu={<PersonalMenu />}><Pages /></AppShell></BrowserRouter>
}

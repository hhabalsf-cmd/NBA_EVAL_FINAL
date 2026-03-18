import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, BarChart3, Search as SearchIcon, Target, Activity } from 'lucide-react'
import { getPerformanceStats } from '../picks/api'

// ── Animated counter ─────────────────────────────────────────────────────────
function AnimatedNumber({
  value,
  decimals = 1,
  prefix = '',
  suffix = '',
}: {
  value: number
  decimals?: number
  prefix?: string
  suffix?: string
}) {
  const [displayed, setDisplayed] = useState(0)
  const started = useRef(false)

  useEffect(() => {
    if (started.current || !value) return
    started.current = true
    const duration = 1400
    const startTime = performance.now()
    const tick = (now: number) => {
      const p = Math.min((now - startTime) / duration, 1)
      const eased = 1 - Math.pow(1 - p, 3)
      setDisplayed(eased * value)
      if (p < 1) requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  }, [value])

  return <>{prefix}{displayed.toFixed(decimals)}{suffix}</>
}

// ── Ghost decorative stat card ────────────────────────────────────────────────
function GhostStatCard({
  player, stat, value, line, isOver, conf,
}: {
  player: string
  stat: string
  value: number
  line: number
  isOver: boolean
  conf: number
}) {
  return (
    <div className="bg-bg-secondary border border-border-subtle rounded-xl p-3 w-40 shadow-lg">
      <div className="text-[9px] text-text-muted uppercase tracking-wider mb-1.5 truncate">{player}</div>
      <div className="flex items-end justify-between gap-2">
        <div>
          <div className="font-mono text-base font-bold text-text-primary leading-none">{value}</div>
          <div className="text-[9px] text-text-muted mt-0.5">{stat} · L{line}</div>
        </div>
        <div className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
          isOver ? 'text-accent-success bg-accent-success/10' : 'text-accent-danger bg-accent-danger/10'
        }`}>
          {isOver ? 'OVER' : 'UNDER'}
        </div>
      </div>
      <div className="mt-2">
        <div className="flex justify-between text-[8px] text-text-muted mb-1">
          <span>Conf</span>
          <span>{conf}%</span>
        </div>
        <div className="h-0.5 bg-bg-elevated rounded-full overflow-hidden">
          <div className="h-full rounded-full bg-accent-success" style={{ width: `${conf}%` }} />
        </div>
      </div>
    </div>
  )
}

const GHOST_CARDS = [
  { player: 'LeBron James', stat: 'PTS', value: 27.5, line: 26.5, isOver: true,  conf: 78 },
  { player: 'S. Curry',     stat: 'PTS', value: 31.2, line: 29.5, isOver: true,  conf: 82 },
  { player: 'N. Jokić',     stat: 'REB', value: 12.1, line: 11.5, isOver: true,  conf: 71 },
  { player: 'A. Edwards',   stat: 'AST', value: 4.2,  line: 5.0,  isOver: false, conf: 68 },
]

// ── Main component ────────────────────────────────────────────────────────────

export default function LandingPage() {
  const { data: stats } = useQuery({
    queryKey: ['performance-stats'],
    queryFn: getPerformanceStats,
    staleTime: 1000 * 60 * 5,
  })

  return (
    <div className="space-y-12 sm:space-y-20">
      {/* Keyframe animations */}
      <style>{`
        @keyframes orbDrift1 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33%       { transform: translate(18px, -22px) scale(1.07); }
          66%       { transform: translate(-10px, -8px) scale(0.96); }
        }
        @keyframes orbDrift2 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          50%       { transform: translate(-20px, 14px) scale(1.1); }
        }
        @keyframes ghostFloat1 {
          0%, 100% { transform: translateY(0px)  rotate(-1deg); }
          50%       { transform: translateY(-10px) rotate(1deg); }
        }
        @keyframes ghostFloat2 {
          0%, 100% { transform: translateY(0px)  rotate(2deg); }
          50%       { transform: translateY(-14px) rotate(-1deg); }
        }
        @keyframes ghostFloat3 {
          0%, 100% { transform: translateY(0px)  rotate(-2deg); }
          50%       { transform: translateY(-8px)  rotate(0deg); }
        }
        @keyframes ghostFloat4 {
          0%, 100% { transform: translateY(0px)  rotate(1deg); }
          50%       { transform: translateY(-11px) rotate(-2deg); }
        }
        @keyframes livePulse {
          0%, 100% { opacity: 1;   box-shadow: 0 0 0 0   rgba(107,191,138,0.5); }
          50%       { opacity: 0.6; box-shadow: 0 0 0 5px rgba(107,191,138,0); }
        }
        @keyframes scanLine {
          0%   { transform: translateX(-100%); }
          100% { transform: translateX(100vw); }
        }
      `}</style>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="relative pt-8 sm:pt-14 pb-10 text-center max-w-3xl mx-auto">

        {/* Background layer — orbs + dot grid */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none rounded-3xl">
          {/* Cyan orb — top-left */}
          <div
            className="absolute -top-20 -left-28 w-80 h-80 rounded-full blur-3xl"
            style={{
              background: 'radial-gradient(circle, var(--accent) 0%, transparent 70%)',
              opacity: 0.13,
              animation: 'orbDrift1 9s ease-in-out infinite',
            }}
          />
          {/* Amber orb — bottom-right */}
          <div
            className="absolute -bottom-12 -right-20 w-64 h-64 rounded-full blur-3xl"
            style={{
              background: 'radial-gradient(circle, var(--accent-warning) 0%, transparent 70%)',
              opacity: 0.09,
              animation: 'orbDrift2 12s ease-in-out infinite',
            }}
          />
          {/* Dot grid */}
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: 'radial-gradient(circle, var(--border-subtle) 1px, transparent 1px)',
              backgroundSize: '30px 30px',
              opacity: 0.5,
            }}
          />
        </div>

        {/* Ghost floating stat cards */}
        <div
          className="absolute top-6 -left-2 sm:-left-14 pointer-events-none select-none hidden sm:block"
          style={{ animation: 'ghostFloat1 7s ease-in-out infinite', opacity: 0.12 }}
        >
          <GhostStatCard {...GHOST_CARDS[0]} />
        </div>
        <div
          className="absolute top-14 -right-2 sm:-right-14 pointer-events-none select-none hidden sm:block"
          style={{ animation: 'ghostFloat2 8.5s ease-in-out infinite', opacity: 0.12 }}
        >
          <GhostStatCard {...GHOST_CARDS[1]} />
        </div>
        <div
          className="absolute bottom-8 -left-6 sm:-left-20 pointer-events-none select-none hidden md:block"
          style={{ animation: 'ghostFloat3 6.5s ease-in-out infinite', opacity: 0.09 }}
        >
          <GhostStatCard {...GHOST_CARDS[2]} />
        </div>
        <div
          className="absolute bottom-16 -right-4 sm:-right-16 pointer-events-none select-none hidden md:block"
          style={{ animation: 'ghostFloat4 9.5s ease-in-out infinite', opacity: 0.09 }}
        >
          <GhostStatCard {...GHOST_CARDS[3]} />
        </div>

        {/* Content */}
        <div className="relative z-10">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 mb-6 px-3.5 py-1.5 rounded-full border border-border-default bg-bg-secondary/80 backdrop-blur-sm">
            <span
              className="w-1.5 h-1.5 rounded-full bg-accent-success flex-shrink-0"
              style={{ animation: 'livePulse 2s ease-in-out infinite' }}
            />
            <span className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">
              ML-Powered Analytics
            </span>
          </div>

          <h1 className="heading-display text-5xl sm:text-6xl md:text-7xl font-bold text-text-primary mb-4 sm:mb-5 leading-none">
            Stop guessing.<br />
            <span className="text-accent">Start evaluating.</span>
          </h1>
          <p className="text-text-secondary text-[15px] sm:text-[17px] leading-relaxed mb-8 sm:mb-10 max-w-lg mx-auto">
            ML models trained on NBA data surface the edge in player props. Know when to bet — and when to pass.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link to="/signup" className="btn btn-primary text-base px-6 py-3 w-full sm:w-auto">
              Get Started Free
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link to="/games" className="btn btn-secondary text-base px-6 py-3 w-full sm:w-auto">
              Today's Games
            </Link>
          </div>
        </div>
      </section>

      {/* ── Live Stats Bar ───────────────────────────────────────────────── */}
      {stats && stats.graded_picks > 0 && (
        <section className="card p-4 sm:p-6 relative overflow-hidden">
          {/* Scanning light streak */}
          <div
            className="absolute top-0 left-0 h-full w-24 pointer-events-none"
            style={{
              background: 'linear-gradient(90deg, transparent 0%, var(--accent) 50%, transparent 100%)',
              opacity: 0.04,
              animation: 'scanLine 5s linear infinite',
            }}
          />
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 sm:gap-5">
            <div className="flex flex-wrap items-center justify-center sm:justify-start gap-6 sm:gap-8">
              <div className="text-center">
                <div className="label-xs mb-1">Win Rate</div>
                <div className={`font-mono text-2xl sm:text-3xl font-bold ${
                  stats.win_rate >= 55 ? 'text-accent-success' : stats.win_rate >= 50 ? 'text-accent' : 'text-accent-danger'
                }`}>
                  <AnimatedNumber value={stats.win_rate} suffix="%" />
                </div>
              </div>
              <div className="h-12 w-px bg-border-subtle hidden sm:block" />
              <div className="text-center">
                <div className="label-xs mb-1">Graded Picks</div>
                <div className="font-mono text-2xl sm:text-3xl font-bold text-text-primary">
                  <AnimatedNumber value={stats.graded_picks} decimals={0} />
                </div>
              </div>
              <div className="h-12 w-px bg-border-subtle hidden sm:block" />
              <div className="text-center">
                <div className="label-xs mb-1">ROI</div>
                <div className={`font-mono text-2xl sm:text-3xl font-bold ${
                  stats.roi > 0 ? 'text-accent-success' : 'text-accent-danger'
                }`}>
                  <AnimatedNumber value={stats.roi} prefix={stats.roi > 0 ? '+' : ''} suffix="%" />
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 text-xs text-text-muted justify-center sm:justify-end">
              <span
                className="w-1.5 h-1.5 rounded-full bg-accent-success flex-shrink-0"
                style={{ animation: 'livePulse 2s ease-in-out infinite' }}
              />
              Updated in real time
            </div>
          </div>
        </section>
      )}

      {/* ── Sample Predictions ──────────────────────────────────────── */}
      <section>
        <div className="mb-6">
          <h2 className="heading-display text-3xl font-semibold text-text-primary">Live Predictions</h2>
          <p className="text-sm text-text-secondary mt-1">See what our ML models produce for today's players</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {GHOST_CARDS.slice(0, 3).map(card => (
            <div key={card.player} className="card p-5 relative overflow-hidden">
              <div
                className="absolute inset-0 pointer-events-none"
                style={{ background: `linear-gradient(135deg, var(--accent)0A 0%, transparent 60%)` }}
              />
              <div className="relative">
                <div className="text-xs text-text-muted uppercase tracking-wider mb-2">{card.player}</div>
                <div className="flex items-end justify-between gap-3">
                  <div>
                    <div className="font-mono text-2xl font-bold text-text-primary">{card.value}</div>
                    <div className="text-xs text-text-muted mt-0.5">{card.stat} prediction</div>
                  </div>
                  <div className="text-right">
                    <div className={`text-xs font-bold px-2 py-1 rounded ${
                      card.isOver ? 'text-accent-success bg-accent-success/10' : 'text-accent-danger bg-accent-danger/10'
                    }`}>
                      {card.isOver ? 'OVER' : 'UNDER'} {card.line}
                    </div>
                    <div className="text-[10px] text-text-muted mt-1">{card.conf}% confidence</div>
                  </div>
                </div>
                <div className="mt-3">
                  <div className="h-1 bg-bg-elevated rounded-full overflow-hidden">
                    <div className="h-full rounded-full bg-accent" style={{ width: `${card.conf}%` }} />
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
        <div className="text-center mt-4">
          <Link to="/signup" className="text-sm text-accent hover:text-accent-hover transition-colors">
            Create a free account to run your own predictions →
          </Link>
        </div>
      </section>

      {/* ── How It Works ─────────────────────────────────────────────────── */}
      <section className="card p-5 sm:p-8 relative overflow-hidden">
        {/* Subtle grid texture */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage: `linear-gradient(var(--border-subtle) 1px, transparent 1px),
                              linear-gradient(90deg, var(--border-subtle) 1px, transparent 1px)`,
            backgroundSize: '40px 40px',
            opacity: 0.025,
          }}
        />
        <div className="relative">
          <h2 className="heading-display text-2xl font-semibold text-text-primary mb-8">How It Works</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 relative">
            {/* Connecting line — desktop only */}
            <div className="absolute top-6 left-[16.67%] right-[16.67%] h-px hidden md:block"
              style={{ background: 'linear-gradient(90deg, transparent, var(--border-default), transparent)' }}
            />

            {([
              { Icon: SearchIcon, step: '01', title: 'Search Player',  desc: "Enter any NBA player's name to begin analysis",                      color: 'var(--accent)' },
              { Icon: BarChart3,  step: '02', title: 'ML Prediction',   desc: 'Our model analyzes historical data, matchups, and trends',           color: 'var(--accent-warning)' },
              { Icon: Target,     step: '03', title: 'Evaluate Lines',  desc: 'Compare predictions to betting lines and save your picks',           color: 'var(--accent-success)' },
            ] as const).map(({ Icon, step, title, desc, color }) => (
              <div key={step} className="flex flex-col items-center text-center gap-4">
                <div className="relative">
                  <div
                    className="w-12 h-12 rounded-2xl flex items-center justify-center"
                    style={{ background: `${color}18`, border: `1px solid ${color}30` }}
                  >
                    <Icon className="w-5 h-5" style={{ color }} />
                  </div>
                  <div className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-bg-secondary border border-border-subtle flex items-center justify-center">
                    <span className="text-[8px] font-mono font-bold text-text-muted">{step}</span>
                  </div>
                </div>
                <div>
                  <h3 className="font-semibold text-text-primary text-sm mb-1.5">{title}</h3>
                  <p className="text-xs text-text-secondary leading-relaxed">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Track Record ─────────────────────────────────────────────────── */}
      {stats && Object.keys(stats.by_stat).length > 0 && (
        <section>
          <div className="mb-6">
            <h2 className="heading-display text-3xl font-semibold text-text-primary">Track Record</h2>
            <p className="text-sm text-text-secondary mt-1">Updated in real time from graded picks</p>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {(['PTS', 'REB', 'AST', 'PRA'] as const).map(stat => {
              const statData = stats.by_stat[stat]
              if (!statData) {
                return (
                  <div key={stat} className="card p-5 text-center opacity-30">
                    <div className="text-[11px] text-text-muted uppercase tracking-wider mb-2">{stat}</div>
                    <div className="font-mono text-2xl font-bold text-text-muted">--</div>
                    <div className="text-xs text-text-muted mt-1">No data</div>
                  </div>
                )
              }
              const isGood = statData.win_rate >= 55
              const isOk   = statData.win_rate >= 50
              const color  = isGood ? 'var(--accent-success)' : isOk ? 'var(--accent)' : 'var(--accent-danger)'
              return (
                <div key={stat} className="card p-5 relative overflow-hidden">
                  {/* Tinted background wash */}
                  <div
                    className="absolute inset-0 pointer-events-none"
                    style={{ background: `linear-gradient(135deg, ${color}0A 0%, transparent 60%)` }}
                  />
                  <div className="relative">
                    <div className="flex items-center justify-between mb-3">
                      <div className="text-[11px] text-text-muted uppercase tracking-wider font-semibold">{stat}</div>
                      <Activity className="w-3 h-3 text-text-muted opacity-40" />
                    </div>
                    <div className="font-mono text-2xl font-bold mb-1" style={{ color }}>
                      {statData.win_rate.toFixed(1)}%
                    </div>
                    <div className="text-xs text-text-secondary mb-3">{statData.wins}W / {statData.total}</div>
                    <div className="h-1 bg-bg-elevated rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{ width: `${statData.win_rate}%`, background: color }}
                      />
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* ── Footer CTA ───────────────────────────────────────────────────── */}
      <section
        className="relative overflow-hidden rounded-2xl p-6 sm:p-10 text-center"
        style={{
          background: 'linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-tertiary) 100%)',
          border: '1px solid var(--border-subtle)',
        }}
      >
        {/* Glow above heading */}
        <div
          className="absolute top-0 left-1/2 -translate-x-1/2 w-72 h-28 blur-3xl pointer-events-none"
          style={{ background: 'var(--accent)', opacity: 0.07 }}
        />
        <div className="relative">
          <h2 className="text-xl font-semibold text-text-primary mb-3 tracking-tight">Ready to find an edge?</h2>
          <p className="text-sm text-text-secondary mb-6 max-w-sm mx-auto">
            Create a free account to get started with ML-powered prop analysis.
          </p>
          <Link to="/signup" className="btn btn-primary text-base px-8 py-3 w-full sm:w-auto">
            Get Started Free
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </section>

      {/* ── Footer Links ────────────────────────────────────────────────── */}
      <div className="flex items-center justify-center gap-6 text-xs text-text-muted pb-4">
        <span>&copy; {new Date().getFullYear()} Bettin' Jrys</span>
        <a href="mailto:contact@bettinjrys.com" className="hover:text-text-secondary transition-colors">Contact</a>
      </div>
    </div>
  )
}

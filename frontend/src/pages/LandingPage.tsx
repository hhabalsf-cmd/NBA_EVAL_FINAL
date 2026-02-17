import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, BarChart3, Search as SearchIcon, Target, TrendingUp } from 'lucide-react'
import BetCard from '../components/BetCard'
import { getPerformanceStats, getTodaysBestBets } from '../api/client'

export default function LandingPage() {
  const [picksVisible, setPicksVisible] = useState(false)
  const picksRef = useRef<HTMLDivElement>(null)

  const { data: stats } = useQuery({
    queryKey: ['performance-stats'],
    queryFn: getPerformanceStats,
    staleTime: 1000 * 60 * 5,
  })

  const { data: bestBets, isLoading: betsLoading, refetch: loadBets } = useQuery({
    queryKey: ['best-bets-landing'],
    queryFn: () => getTodaysBestBets(5, 3),
    enabled: picksVisible,
    staleTime: 1000 * 60 * 30,
  })

  const handleLoadPicks = () => {
    setPicksVisible(true)
    loadBets()
  }

  return (
    <div className="space-y-20">
      {/* Hero */}
      <section className="pt-10 pb-4 text-center max-w-2xl mx-auto">
        <h1 className="text-4xl md:text-5xl font-bold text-text-primary tracking-tight mb-5 leading-tight">
          Stop guessing.<br />
          <span className="text-accent">Start evaluating.</span>
        </h1>
        <p className="text-text-secondary text-[17px] leading-relaxed mb-10 max-w-lg mx-auto">
          ML models trained on NBA data surface the edge in player props. Know when to bet — and when to pass.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <Link to="/app" className="btn btn-primary text-base px-6 py-3">
            Start Analyzing
            <ArrowRight className="w-4 h-4" />
          </Link>
          <Link to="/games" className="btn btn-secondary text-base px-6 py-3">
            Today's Games
          </Link>
        </div>
      </section>

      {/* Live Stats Bar */}
      {stats && stats.graded_picks > 0 && (
        <section className="card p-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-5">
            <div className="flex flex-wrap items-center gap-8">
              <div className="text-center">
                <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Win Rate</div>
                <div className={`font-mono text-3xl font-bold ${
                  stats.win_rate >= 55 ? 'text-accent-success' : stats.win_rate >= 50 ? 'text-accent' : 'text-accent-danger'
                }`}>
                  {stats.win_rate.toFixed(1)}%
                </div>
              </div>
              <div className="h-12 w-px bg-border-subtle hidden sm:block" />
              <div className="text-center">
                <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">Graded Picks</div>
                <div className="font-mono text-3xl font-bold text-text-primary">
                  {stats.graded_picks}
                </div>
              </div>
              <div className="h-12 w-px bg-border-subtle hidden sm:block" />
              <div className="text-center">
                <div className="text-[11px] text-text-muted uppercase tracking-wider mb-1">ROI</div>
                <div className={`font-mono text-3xl font-bold ${stats.roi > 0 ? 'text-accent-success' : 'text-accent-danger'}`}>
                  {stats.roi > 0 ? '+' : ''}{stats.roi.toFixed(1)}%
                </div>
              </div>
            </div>
            <div className="text-xs text-text-muted">Updated in real time</div>
          </div>
        </section>
      )}

      {/* Top Picks Preview */}
      <section ref={picksRef}>
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-semibold text-text-primary tracking-tight">Highest Edge Plays</h2>
            <p className="text-sm text-text-secondary mt-1">Today's best opportunities by model edge</p>
          </div>
          {!picksVisible && (
            <button onClick={handleLoadPicks} className="btn btn-primary text-sm">
              <TrendingUp className="w-4 h-4" />
              Load Picks
            </button>
          )}
        </div>

        {picksVisible && (
          betsLoading ? (
            <div className="card p-12 flex items-center justify-center gap-3">
              <div className="spinner" />
              <span className="text-text-secondary text-sm">Analyzing today's props…</span>
            </div>
          ) : bestBets && bestBets.bets.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {bestBets.bets.map((bet, index) => (
                <BetCard key={`${bet.player}-${bet.stat}`} bet={bet} rank={index + 1} />
              ))}
            </div>
          ) : (
            <div className="card p-10 text-center">
              <p className="text-sm text-text-secondary">No picks available right now. Check back before game time.</p>
            </div>
          )
        )}

        {!picksVisible && (
          <div className="card p-10 text-center border-dashed">
            <p className="text-sm text-text-secondary">Click "Load Picks" to see today's highest-edge plays.</p>
          </div>
        )}
      </section>

      {/* How It Works */}
      <section className="card p-8">
        <h2 className="text-lg font-semibold text-text-primary mb-8 tracking-tight">How It Works</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <div className="flex gap-4">
            <div className="flex-shrink-0 w-9 h-9 rounded-lg bg-accent/10 flex items-center justify-center">
              <SearchIcon className="w-4 h-4 text-accent" />
            </div>
            <div>
              <h3 className="font-medium text-text-primary text-sm mb-1">Search Player</h3>
              <p className="text-xs text-text-secondary leading-relaxed">Enter any NBA player's name to begin analysis</p>
            </div>
          </div>
          <div className="flex gap-4">
            <div className="flex-shrink-0 w-9 h-9 rounded-lg bg-accent/10 flex items-center justify-center">
              <BarChart3 className="w-4 h-4 text-accent" />
            </div>
            <div>
              <h3 className="font-medium text-text-primary text-sm mb-1">ML Prediction</h3>
              <p className="text-xs text-text-secondary leading-relaxed">Our model analyzes historical data, matchups, and trends</p>
            </div>
          </div>
          <div className="flex gap-4">
            <div className="flex-shrink-0 w-9 h-9 rounded-lg bg-accent/10 flex items-center justify-center">
              <Target className="w-4 h-4 text-accent" />
            </div>
            <div>
              <h3 className="font-medium text-text-primary text-sm mb-1">Evaluate Lines</h3>
              <p className="text-xs text-text-secondary leading-relaxed">Compare predictions to betting lines and save your picks</p>
            </div>
          </div>
        </div>
      </section>

      {/* Track Record */}
      {stats && Object.keys(stats.by_stat).length > 0 && (
        <section>
          <div className="mb-6">
            <h2 className="text-2xl font-semibold text-text-primary tracking-tight">Track Record</h2>
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
              return (
                <div key={stat} className="card p-5 text-center">
                  <div className="text-[11px] text-text-muted uppercase tracking-wider mb-2">{stat}</div>
                  <div className={`font-mono text-2xl font-bold ${
                    statData.win_rate >= 55 ? 'text-accent-success' : statData.win_rate >= 50 ? 'text-accent' : 'text-accent-danger'
                  }`}>
                    {statData.win_rate.toFixed(1)}%
                  </div>
                  <div className="text-xs text-text-secondary mt-1">{statData.wins}W / {statData.total}</div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* Footer CTA */}
      <section className="card p-10 text-center">
        <h2 className="text-xl font-semibold text-text-primary mb-3 tracking-tight">Ready to find an edge?</h2>
        <p className="text-sm text-text-secondary mb-6 max-w-sm mx-auto">
          ML-powered prop analysis in seconds. No signup required to start.
        </p>
        <Link to="/app" className="btn btn-primary text-base px-8 py-3">
          Start Analyzing
          <ArrowRight className="w-4 h-4" />
        </Link>
      </section>
    </div>
  )
}

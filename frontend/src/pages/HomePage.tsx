import { useQuery } from '@tanstack/react-query'
import { ArrowRight, BarChart3, Search as SearchIcon, Target } from 'lucide-react'
import { Link } from 'react-router-dom'
import PlayerSearch from '../components/PlayerSearch'
import { getPerformanceStats } from '../api/client'

export default function HomePage() {
  const { data: stats } = useQuery({
    queryKey: ['performance-stats'],
    queryFn: getPerformanceStats,
    staleTime: 1000 * 60 * 5,
  })


  return (
    <div className="space-y-12">
      {/* Hero */}
      <section className="pt-6 pb-2">
        <h1 className="text-3xl md:text-4xl font-bold text-text-primary tracking-tight mb-3">
          Evaluate Player Props
        </h1>
        <p className="text-text-secondary mb-8 max-w-lg text-[15px] leading-relaxed">
          ML-powered predictions for points, rebounds, assists, and combined stats.
        </p>
        <PlayerSearch
          autoFocus
          placeholder="Search for a player (e.g., Nikola Jokic)"
        />
      </section>

      {/* Performance Stats Bar */}
      {stats && stats.graded_picks > 0 && (
        <section className="card p-5">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-5">
            <div className="flex flex-wrap items-center gap-6">
              <div>
                <div className="label-xs mb-1">Record</div>
                <div className="font-mono text-xl font-semibold">
                  <span className="text-accent-success">{stats.wins}W</span>
                  <span className="text-text-muted mx-1">-</span>
                  <span className="text-accent-danger">{stats.losses}L</span>
                </div>
              </div>
              <div className="h-8 w-px bg-border-subtle hidden sm:block" />
              <div>
                <div className="label-xs mb-1">Win Rate</div>
                <div className={`font-mono text-xl font-semibold ${
                  stats.win_rate >= 55 ? 'text-accent-success' : stats.win_rate >= 50 ? 'text-accent' : 'text-accent-danger'
                }`}>
                  {stats.win_rate.toFixed(1)}%
                </div>
              </div>
              <div className="h-8 w-px bg-border-subtle hidden sm:block" />
              <div>
                <div className="label-xs mb-1">ROI</div>
                <div className={`font-mono text-xl font-semibold ${stats.roi > 0 ? 'text-accent-success' : 'text-accent-danger'}`}>
                  {stats.roi > 0 ? '+' : ''}{stats.roi.toFixed(1)}%
                </div>
              </div>
            </div>
            <Link to="/history" className="btn btn-secondary text-sm">
              View History
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </section>
      )}

      {/* Top Picks — temporarily unavailable */}
      <section>
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-text-primary tracking-tight">Top Picks</h2>
          <span className="text-sm text-text-muted">Highest edge opportunities</span>
        </div>
        <div className="card p-10 text-center opacity-60">
          <h3 className="text-base font-medium text-text-primary mb-2">Coming Soon</h3>
          <p className="text-sm text-text-secondary max-w-md mx-auto leading-relaxed">
            Auto-generated top picks will appear here. Use the search above to manually evaluate a player.
          </p>
        </div>
      </section>

      {/* Performance by Stat */}
      <section>
        <h2 className="text-xl font-semibold text-text-primary tracking-tight mb-6">Performance by Stat</h2>
        {stats && Object.keys(stats.by_stat).length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {['PTS', 'REB', 'AST', 'PRA'].map(stat => {
              const statData = stats.by_stat[stat]
              if (!statData) {
                return (
                  <div key={stat} className="card card-accent p-5 text-center opacity-30">
                    <div className="label-xs mb-2">{stat}</div>
                    <div className="font-mono text-2xl font-bold text-text-muted">--</div>
                    <div className="text-xs text-text-muted mt-1">No data</div>
                  </div>
                )
              }
              return (
                <div key={stat} className="card card-accent p-5 text-center">
                  <div className="label-xs mb-2">{stat}</div>
                  <div className={`font-mono text-2xl font-bold ${
                    statData.win_rate >= 55 ? 'text-accent-success' : statData.win_rate >= 50 ? 'text-accent' : 'text-accent-danger'
                  }`}>
                    {statData.win_rate.toFixed(1)}%
                  </div>
                  <div className="text-xs text-text-secondary mt-1">{statData.wins}W / {statData.total} picks</div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="card p-8 text-center">
            <p className="text-sm text-text-secondary">No graded picks yet. Save picks and they'll appear here once graded.</p>
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
    </div>
  )
}

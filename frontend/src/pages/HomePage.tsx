import { useQuery } from '@tanstack/react-query'
import PlayerSearch from '../components/PlayerSearch'
import BetCard from '../components/BetCard'
import { getPerformanceStats, getTodaysBestBets } from '../api/client'

export default function HomePage() {
  const { data: stats } = useQuery({
    queryKey: ['performance-stats'],
    queryFn: getPerformanceStats,
    staleTime: 1000 * 60 * 5,
  })

  const { data: bestBets, isLoading: betsLoading } = useQuery({
    queryKey: ['best-bets'],
    queryFn: () => getTodaysBestBets(5, 3),
    enabled: false,
    staleTime: 1000 * 60 * 30,
  })

  return (
    <div className="space-y-10">
      {/* Hero */}
      <section className="py-10">
        <h1 className="text-3xl md:text-4xl font-bold text-text-primary mb-2">
          Evaluate Player Props
        </h1>
        <p className="text-text-secondary mb-6 max-w-xl">
          ML-powered predictions for points, rebounds, assists, and combined stats.
        </p>
        <PlayerSearch
          autoFocus
          placeholder="Search for a player (e.g., Nikola Jokic)"
        />
      </section>

      {/* Performance Stats Bar */}
      {stats && stats.graded_picks > 0 && (
        <section className="card p-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-5">
              <div>
                <div className="text-[11px] text-text-muted uppercase tracking-wider mb-0.5">Record</div>
                <div className="font-mono text-lg font-bold">
                  <span className="text-accent-success">{stats.wins}W</span>
                  <span className="text-text-muted mx-0.5">-</span>
                  <span className="text-accent-danger">{stats.losses}L</span>
                </div>
              </div>
              <div className="h-8 w-px bg-border-subtle" />
              <div>
                <div className="text-[11px] text-text-muted uppercase tracking-wider mb-0.5">Win Rate</div>
                <div className={`font-mono text-lg font-bold ${stats.win_rate >= 55 ? 'text-accent-success' : stats.win_rate >= 50 ? 'text-accent-gold' : 'text-accent-danger'}`}>
                  {stats.win_rate.toFixed(1)}%
                </div>
              </div>
              <div className="h-8 w-px bg-border-subtle" />
              <div>
                <div className="text-[11px] text-text-muted uppercase tracking-wider mb-0.5">ROI</div>
                <div className={`font-mono text-lg font-bold ${stats.roi > 0 ? 'text-accent-success' : 'text-accent-danger'}`}>
                  {stats.roi > 0 ? '+' : ''}{stats.roi.toFixed(1)}%
                </div>
              </div>
            </div>
            <a href="/history" className="btn btn-secondary text-sm">View History</a>
          </div>
        </section>
      )}

      {/* Top Picks */}
      <section>
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-xl font-bold text-text-primary">Top Picks</h2>
          <span className="text-sm text-text-muted">Highest edge opportunities</span>
        </div>

        {betsLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="spinner" />
            <span className="ml-3 text-text-secondary text-sm">Analyzing today's props...</span>
          </div>
        ) : bestBets && bestBets.bets.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {bestBets.bets.map((bet, index) => (
              <BetCard key={`${bet.player}-${bet.stat}`} bet={bet} rank={index + 1} />
            ))}
          </div>
        ) : (
          <div className="card p-8 text-center">
            <h3 className="text-base font-semibold text-text-primary mb-1.5">Search for Players</h3>
            <p className="text-sm text-text-secondary max-w-md mx-auto">
              Use the search above to find a player and get ML-powered predictions.
              Top picks will appear here when games are available.
            </p>
          </div>
        )}
      </section>

      {/* Performance by Stat */}
      <section>
        <h2 className="text-xl font-bold text-text-primary mb-5">Performance by Stat</h2>
        {stats && Object.keys(stats.by_stat).length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {['PTS', 'REB', 'AST', 'PRA'].map(stat => {
              const statData = stats.by_stat[stat]
              if (!statData) {
                return (
                  <div key={stat} className="card p-4 text-center opacity-40">
                    <div className="text-[11px] text-text-muted uppercase tracking-wider mb-2">{stat}</div>
                    <div className="font-mono text-2xl font-bold text-text-muted">--</div>
                    <div className="text-xs text-text-muted">No data</div>
                  </div>
                )
              }
              return (
                <div key={stat} className="card p-4 text-center">
                  <div className="text-[11px] text-text-muted uppercase tracking-wider mb-2">{stat}</div>
                  <div className={`font-mono text-2xl font-bold ${statData.win_rate >= 55 ? 'text-accent-success' : statData.win_rate >= 50 ? 'text-accent-gold' : 'text-accent-danger'}`}>
                    {statData.win_rate.toFixed(1)}%
                  </div>
                  <div className="text-xs text-text-secondary">{statData.wins}W / {statData.total} picks</div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="card p-6 text-center">
            <p className="text-sm text-text-secondary">No graded picks yet. Save picks and they'll appear here once graded.</p>
          </div>
        )}
      </section>

      {/* How It Works */}
      <section className="card p-8">
        <h2 className="text-lg font-bold text-text-primary mb-6">How It Works</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <div className="text-sm font-mono font-bold text-accent mb-2">01</div>
            <h3 className="font-semibold text-text-primary text-sm mb-1">Search Player</h3>
            <p className="text-xs text-text-secondary">Enter any NBA player's name to begin analysis</p>
          </div>
          <div>
            <div className="text-sm font-mono font-bold text-accent mb-2">02</div>
            <h3 className="font-semibold text-text-primary text-sm mb-1">ML Prediction</h3>
            <p className="text-xs text-text-secondary">Our model analyzes historical data, matchups, and trends</p>
          </div>
          <div>
            <div className="text-sm font-mono font-bold text-accent mb-2">03</div>
            <h3 className="font-semibold text-text-primary text-sm mb-1">Evaluate Lines</h3>
            <p className="text-xs text-text-secondary">Compare predictions to betting lines and save your picks</p>
          </div>
        </div>
      </section>
    </div>
  )
}

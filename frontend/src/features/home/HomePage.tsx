import { useQuery } from '@tanstack/react-query'
import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { motion, type Variants } from 'framer-motion'
import PlayerSearch from '../../shared/components/PlayerSearch'
import ModelAccuracyBanner from '../../shared/components/ModelAccuracyBanner'
import BestBetsSection from './BestBetsSection'
import AdminLinesSection from './AdminLinesSection'
import { homeHeroCopy, howItWorksSteps, type HowItWorksStep } from './copy'
import { getPerformanceStats } from '../picks/api'
import { PREDICTIONS_ENABLED } from '../../shared/lib/flags'
import { useTilt } from '../../shared/hooks/useTilt'

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 16 },
  show:   { opacity: 1, y: 0 },
}

const stagger: Variants = {
  hidden: {},
  show:   { transition: { staggerChildren: 0.1, delayChildren: 0.04 } },
}

const statCardVariant: Variants = {
  hidden: { opacity: 0, y: 12, scale: 0.97 },
  show:   { opacity: 1, y: 0, scale: 1 },
}

function StatCard({ stat, winRate, wins, total }: { stat: string; winRate: number; wins: number; total: number }) {
  const tilt = useTilt({ maxTilt: 10, scale: 1.04 })
  return (
    <motion.div
      ref={tilt.ref}
      onMouseMove={tilt.onMouseMove}
      onMouseEnter={tilt.onMouseEnter}
      onMouseLeave={tilt.onMouseLeave}
      style={tilt.style}
      className="card card-3d card-accent p-5 text-center"
      variants={statCardVariant}
      transition={{ duration: 0.3, ease: 'easeOut' }}
    >
      <div className="tilt-glare" />
      <div className="label-xs mb-2">{stat}</div>
      <div className={`font-mono text-2xl font-bold ${
        winRate >= 55 ? 'text-accent-success' : winRate >= 50 ? 'text-accent' : 'text-accent-danger'
      }`}>
        {winRate.toFixed(1)}%
      </div>
      <div className="text-xs text-text-secondary mt-1">{wins}W / {total} picks</div>
    </motion.div>
  )
}

function HowItWorksIcon({ icon: Icon, title, desc }: HowItWorksStep) {
  const tilt = useTilt({ maxTilt: 12, scale: 1.08 })
  return (
    <motion.div
      className="flex gap-4"
      variants={fadeUp}
      transition={{ duration: 0.3, ease: 'easeOut' }}
    >
      <motion.div
        ref={tilt.ref}
        onMouseMove={tilt.onMouseMove}
        onMouseEnter={tilt.onMouseEnter}
        onMouseLeave={tilt.onMouseLeave}
        style={tilt.style}
        className="flex-shrink-0 w-9 h-9 rounded-lg bg-accent/10 flex items-center justify-center card-3d"
      >
        <Icon className="w-4 h-4 text-accent" />
      </motion.div>
      <div>
        <h3 className="font-medium text-text-primary text-sm mb-1">{title}</h3>
        <p className="text-xs text-text-secondary leading-relaxed">{desc}</p>
      </div>
    </motion.div>
  )
}

export default function HomePage() {
  const hero = homeHeroCopy(PREDICTIONS_ENABLED)
  const steps = howItWorksSteps(PREDICTIONS_ENABLED)

  // Pick performance is a betting track record. With predictions gated off the
  // home page does not lead with it — the same data stays on /picks, which is
  // the user's own record rather than a claim about the model.
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['performance-stats'],
    queryFn: getPerformanceStats,
    staleTime: 1000 * 60 * 5,
    enabled: PREDICTIONS_ENABLED,
  })

  return (
    <motion.div className="space-y-12" variants={stagger} initial="hidden" animate="show">
      {/* Hero */}
      <motion.section
        className="pt-6 pb-2"
        variants={fadeUp}
        transition={{ duration: 0.4, ease: 'easeOut' }}
      >
        <h1 className="heading-display text-4xl md:text-5xl font-bold text-text-primary mb-3">
          {hero.heading}
        </h1>
        <p className="text-text-secondary mb-8 max-w-lg text-[15px] leading-relaxed">
          {hero.subheading}
        </p>
        <PlayerSearch
          autoFocus
          placeholder="Search for a player (e.g., Nikola Jokic)"
        />
      </motion.section>

      {/* Performance Stats Bar */}
      {PREDICTIONS_ENABLED && statsLoading && (
        <motion.section className="card p-5" variants={fadeUp} transition={{ duration: 0.38, ease: 'easeOut' }}>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-5 animate-pulse">
            <div className="space-y-2">
              <div className="skeleton h-4 w-24 rounded" />
              <div className="skeleton h-6 w-32 rounded" />
            </div>
            <div className="flex gap-6">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="text-center space-y-1">
                  <div className="skeleton h-3 w-14 rounded mx-auto" />
                  <div className="skeleton h-6 w-10 rounded mx-auto" />
                </div>
              ))}
            </div>
          </div>
        </motion.section>
      )}
      {PREDICTIONS_ENABLED && stats && stats.graded_picks > 0 && (
        <motion.section
          className="card p-5"
          variants={fadeUp}
          transition={{ duration: 0.38, ease: 'easeOut' }}
        >
          <ModelAccuracyBanner className="mb-5" />
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
            <Link to="/picks" className="btn btn-secondary text-sm">
              View History
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </motion.section>
      )}

      {/* Best Bets Today — model recommendations, gated */}
      {PREDICTIONS_ENABLED && (
        <motion.section variants={fadeUp} transition={{ duration: 0.38, ease: 'easeOut' }}>
          <BestBetsSection />
        </motion.section>
      )}

      {/* Admin line entry — never gated: it feeds the closing-line record */}
      <motion.section variants={fadeUp} transition={{ duration: 0.38, ease: 'easeOut' }}>
        <AdminLinesSection />
      </motion.section>

      {/* Performance by Stat */}
      {PREDICTIONS_ENABLED && (
        <motion.section variants={fadeUp} transition={{ duration: 0.38, ease: 'easeOut' }}>
          <h2 className="heading-display text-2xl font-semibold text-text-primary mb-4">Performance by Stat</h2>
          <ModelAccuracyBanner className="mb-6" />
          {stats && Object.keys(stats.by_stat).length > 0 ? (
            <motion.div
              className="grid grid-cols-2 sm:grid-cols-4 gap-4"
              variants={stagger}
              initial="hidden"
              animate="show"
            >
              {['PTS', 'REB', 'AST', 'PRA'].map(stat => {
                const statData = stats.by_stat[stat]
                if (!statData) {
                  return (
                    <motion.div
                      key={stat}
                      className="card card-accent p-5 text-center opacity-30"
                      variants={statCardVariant}
                      transition={{ duration: 0.3, ease: 'easeOut' }}
                    >
                      <div className="label-xs mb-2">{stat}</div>
                      <div className="font-mono text-2xl font-bold text-text-muted">--</div>
                      <div className="text-xs text-text-muted mt-1">No data</div>
                    </motion.div>
                  )
                }
                return (
                  <StatCard
                    key={stat}
                    stat={stat}
                    winRate={statData.win_rate}
                    wins={statData.wins}
                    total={statData.total}
                  />
                )
              })}
            </motion.div>
          ) : (
            <motion.div
              className="card p-8 text-center"
              variants={fadeUp}
              transition={{ duration: 0.38, ease: 'easeOut' }}
            >
              <p className="text-sm text-text-secondary">No graded picks yet. Save picks and they'll appear here once graded.</p>
            </motion.div>
          )}
        </motion.section>
      )}

      {/* How It Works */}
      <motion.section
        className="card p-8"
        variants={fadeUp}
        transition={{ duration: 0.38, ease: 'easeOut' }}
      >
        <h2 className="heading-display text-2xl font-semibold text-text-primary mb-8">How It Works</h2>
        <motion.div
          className="grid grid-cols-1 md:grid-cols-3 gap-8"
          variants={stagger}
          initial="hidden"
          animate="show"
        >
          {steps.map(({ icon, title, desc }) => (
            <HowItWorksIcon key={title} icon={icon} title={title} desc={desc} />
          ))}
        </motion.div>
      </motion.section>
    </motion.div>
  )
}

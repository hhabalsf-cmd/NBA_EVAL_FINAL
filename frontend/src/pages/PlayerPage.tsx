import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Check, Loader2, Zap, PlaySquare, FlaskConical } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence, type Variants } from 'framer-motion'
import { usePrediction } from '../hooks/usePrediction'
import PredictionCard from '../components/PredictionCard'
import StatChartModal from '../components/StatChartModal'
import PlayerSearch from '../components/PlayerSearch'
import { evaluateLine, createPick, LineEvaluation, getPlayerOdds, getTeamInjuries, TeamInjuryInfo } from '../api/client'
import { getNbaHeadshotUrl } from '../utils/nba'

const STATS = ['PTS', 'REB', 'AST', 'PRA'] as const

const cardContainer: Variants = {
  hidden: {},
  show:   { transition: { staggerChildren: 0.08, delayChildren: 0.05 } },
}

const cardItem: Variants = {
  hidden: { opacity: 0, y: 18 },
  show:   { opacity: 1, y: 0 },
}

const sectionFade: Variants = {
  hidden: { opacity: 0, y: 10 },
  show:   { opacity: 1, y: 0 },
}

export default function PlayerPage() {
  const { playerName } = useParams<{ playerName: string }>()
  const navigate = useNavigate()
  const { isLoading, progress, message, result, error, predict } = usePrediction()

  const [lineInputs, setLineInputs] = useState<Record<string, string>>({})
  const [allEvaluations, setAllEvaluations] = useState<LineEvaluation[]>([])
  const [isEvaluatingAll, setIsEvaluatingAll] = useState(false)
  const [chartStat, setChartStat] = useState<string | null>(null)

  useEffect(() => {
    if (playerName) {
      setLineInputs({})
      setAllEvaluations([])
      predict(decodeURIComponent(playerName))
    }
  }, [playerName, predict])

  const { data: injuries } = useQuery({
    queryKey: ['team-injuries', playerName],
    queryFn: () => getTeamInjuries(decodeURIComponent(playerName!)),
    enabled: !!playerName && !!result,
    staleTime: 1000 * 60 * 30,
  })

  const { data: odds, isLoading: oddsLoading } = useQuery({
    queryKey: ['player-odds', playerName],
    queryFn: () => getPlayerOdds(decodeURIComponent(playerName!)),
    enabled: !!playerName && !!result,
    staleTime: 1000 * 60 * 30,
  })

  useEffect(() => {
    if (!odds || !odds.found) return
    setLineInputs(prev => {
      const updates: Record<string, string> = { ...prev }
      for (const stat of STATS) {
        const val = odds[stat as keyof typeof odds]
        if (typeof val === 'number' && !prev[stat]) {
          updates[stat] = String(val)
        }
      }
      return updates
    })
  }, [odds])

  const handleEvaluateAll = async () => {
    if (!result) return
    const statsToEval = STATS.filter(s => lineInputs[s] && result.predictions[s])
    if (statsToEval.length === 0) return

    setIsEvaluatingAll(true)
    setAllEvaluations([])
    try {
      const results = await Promise.all(
        statsToEval.map(stat => {
          const line = parseFloat(lineInputs[stat])
          const prediction = result.predictions[stat]?.prediction
          return evaluateLine(result.player_name, stat, line, prediction)
        })
      )
      setAllEvaluations(results)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to evaluate lines'
      alert(`Evaluation failed: ${msg}`)
    } finally {
      setIsEvaluatingAll(false)
    }
  }

  const buildSavePick = (evalData: LineEvaluation) => async () => {
    if (!result) return
    const direction = evalData.recommendation.includes('OVER') ? 'OVER' : 'UNDER'
    await createPick({
      player: result.player_name,
      player_id: result.player_id,
      team_abbrev: result.team_abbrev || undefined,
      stat: evalData.stat,
      line: evalData.line,
      prediction: evalData.prediction,
      direction,
      edge: evalData.diff_pct,
      confidence: evalData.confidence || undefined,
      opponent: result.game_info?.opponent,
      is_home: result.game_info?.is_home,
      model_type: result.model_type,
      game_date: result.game_info?.game_date?.split('T')[0],
      prob_over: evalData.prob_over,
    })
  }

  // ── Skeleton loading state ───────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="space-y-8">
        {/* Skeleton header */}
        <div className="flex items-center gap-4">
          <div className="skeleton w-24 h-24 rounded-2xl flex-shrink-0" />
          <div className="flex-1 space-y-3">
            <div className="skeleton h-7 w-44 rounded-lg" />
            <div className="skeleton h-4 w-20 rounded" />
            <div className="skeleton h-4 w-36 rounded" />
          </div>
        </div>

        {/* Progress indicator */}
        <div className="flex flex-col items-center gap-3 py-6">
          <span className="text-3xl basketball-bounce">🏀</span>
          <div className="text-sm text-text-secondary font-medium">{message}</div>
          <div className="w-64 progress-bar">
            <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
          </div>
          <div className="text-xs text-text-muted font-mono">{progress}% complete</div>
        </div>

        {/* Skeleton prediction cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="card p-5 space-y-4">
              <div className="skeleton h-3 w-16 rounded" />
              <div className="skeleton h-10 w-20 rounded-lg" />
              <div className="skeleton h-3 w-20 rounded" />
              <div className="skeleton h-2 w-full rounded-full" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-24">
        <h2 className="text-lg font-medium text-text-primary mb-2">Couldn't Load Predictions</h2>
        <p className="text-sm text-text-secondary mb-6">{error}</p>
        <button onClick={() => navigate('/app')} className="btn btn-primary">Back to Search</button>
      </div>
    )
  }

  if (!result) return null

  const hasOdds = odds?.found
  const hasAnyLine = STATS.some(s => lineInputs[s])

  return (
    <div className="space-y-8">
      {/* Header */}
      <motion.section
        variants={sectionFade}
        initial="hidden"
        animate="show"
        transition={{ duration: 0.35, ease: 'easeOut' }}
      >
        <div className="flex items-center gap-3 mb-4">
          <button
            onClick={() => navigate('/app')}
            className="text-sm text-text-muted hover:text-text-primary flex items-center gap-1.5 transition-colors flex-shrink-0 py-1"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </button>
          <div className="flex-1 max-w-sm hidden sm:block">
            <PlayerSearch placeholder="Search another player…" replace />
          </div>
          <Link
            to={`/research/${encodeURIComponent(result.player_name)}`}
            className="btn btn-secondary text-xs px-3 py-1.5 flex items-center gap-1.5 flex-shrink-0"
          >
            <FlaskConical className="w-3.5 h-3.5" />
            Research
          </Link>
        </div>
        <div className="flex items-center gap-4 sm:gap-5">
          <img
            src={getNbaHeadshotUrl(result.player_id)}
            alt={result.player_name}
            className="w-18 h-18 sm:w-24 sm:h-24 md:w-28 md:h-28 rounded-2xl object-cover bg-bg-secondary shadow-lg shadow-black/20 flex-shrink-0"
            onError={e => { (e.target as HTMLImageElement).src = getNbaHeadshotUrl(0) }}
          />
          <div className="flex-1 min-w-0">
            <h1 className="text-xl sm:text-2xl md:text-3xl font-bold text-text-primary tracking-tight">{result.player_name}</h1>
            {result.team_abbrev && (
              <p className="text-sm text-text-secondary mt-0.5">{result.team_abbrev}</p>
            )}
            <div className="flex items-center gap-2 sm:gap-3 mt-2 flex-wrap">
              {oddsLoading && (
                <span className="flex items-center gap-1.5 text-xs text-text-muted">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Fetching odds…
                </span>
              )}
              {hasOdds && !oddsLoading && (
                <span className="flex items-center gap-1 px-2 py-1 rounded-md bg-accent/10 text-accent text-[11px] font-medium">
                  <Zap className="w-3 h-3" />
                  Live odds
                </span>
              )}
              <span className="text-[11px] sm:text-xs text-text-muted font-mono">{result.games_trained_on} games</span>
              {result.avg_min_l10 != null && (
                <span className="text-[11px] sm:text-xs text-text-muted font-mono">L10 MIN: {result.avg_min_l10.toFixed(1)}</span>
              )}
            </div>
          </div>
        </div>
        {/* Mobile search */}
        <div className="sm:hidden mt-4">
          <PlayerSearch placeholder="Search another player…" replace />
        </div>
      </motion.section>

      {/* Game Info */}
      {result.game_info && (
        <motion.section
          className="card p-4 sm:p-5"
          variants={sectionFade}
          initial="hidden"
          animate="show"
          transition={{ duration: 0.35, ease: 'easeOut', delay: 0.08 }}
        >
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
            <div>
              <span className="text-text-muted">Matchup: </span>
              <span className="text-text-primary font-medium">{result.game_info.matchup}</span>
            </div>
            <div>
              <span className="text-text-muted">Location: </span>
              <span className="text-text-primary font-medium">{result.game_info.is_home ? 'Home' : 'Away'}</span>
            </div>
            {result.opponent_context && (
              <div>
                <span className="text-text-muted">Opp Def: </span>
                <span className="text-text-primary font-medium">
                  {result.opponent_context.def_rank} ({result.opponent_context.def_rating.toFixed(1)})
                </span>
              </div>
            )}
          </div>

          {result.vs_stats && result.vs_stats.games > 0 && (
            <div className="mt-4 pt-4 border-t border-border-subtle">
              <div className="text-xs text-text-muted mb-2">
                vs {result.game_info.opponent} ({result.vs_stats.games} games)
              </div>
              <div className="flex gap-5 text-sm">
                <span>
                  <span className="text-text-muted">PTS:</span>{' '}
                  <span className="text-text-primary font-medium">{result.vs_stats.avg_pts.toFixed(1)}</span>
                </span>
                <span>
                  <span className="text-text-muted">REB:</span>{' '}
                  <span className="text-text-primary font-medium">{result.vs_stats.avg_reb.toFixed(1)}</span>
                </span>
                <span>
                  <span className="text-text-muted">AST:</span>{' '}
                  <span className="text-text-primary font-medium">{result.vs_stats.avg_ast.toFixed(1)}</span>
                </span>
              </div>
            </div>
          )}
        </motion.section>
      )}

      {/* Injury Report */}
      {injuries && (injuries.team || injuries.opponent) &&
        ((injuries.team?.out.length ?? 0) > 0 ||
          (injuries.team?.questionable.length ?? 0) > 0 ||
          (injuries.opponent?.out.length ?? 0) > 0 ||
          (injuries.opponent?.questionable.length ?? 0) > 0) && (
        <motion.section
          className="card p-5"
          variants={sectionFade}
          initial="hidden"
          animate="show"
          transition={{ duration: 0.35, ease: 'easeOut', delay: 0.14 }}
        >
          <div className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
            Injury Report
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {injuries.team && <InjuryColumn info={injuries.team} label="Your Team" />}
            {injuries.opponent && <InjuryColumn info={injuries.opponent} label="Opponent" />}
          </div>
        </motion.section>
      )}

      {/* Predictions Grid */}
      <section>
        <h2 className="text-lg font-semibold text-text-primary mb-5 tracking-tight">ML Predictions</h2>
        <motion.div
          className="grid grid-cols-2 md:grid-cols-4 gap-4"
          variants={cardContainer}
          initial="hidden"
          animate="show"
        >
          {STATS.map(stat => {
            const prediction = result.predictions[stat]
            if (!prediction) return null
            return (
              <motion.div
                key={stat}
                variants={cardItem}
                transition={{ duration: 0.32, ease: 'easeOut' }}
              >
                <PredictionCard
                  stat={stat}
                  prediction={prediction}
                  onChartClick={() => setChartStat(stat)}
                />
              </motion.div>
            )
          })}
        </motion.div>
      </section>

      {/* Stat Chart Modal */}
      {chartStat && result.game_log && result.game_log.length > 0 && (
        <StatChartModal
          stat={chartStat}
          gameLog={result.game_log}
          onClose={() => setChartStat(null)}
        />
      )}

      {/* Line Evaluation */}
      <motion.section
        className="card p-4 sm:p-6"
        variants={sectionFade}
        initial="hidden"
        animate="show"
        transition={{ duration: 0.35, ease: 'easeOut', delay: 0.28 }}
      >
        <div className="flex items-center justify-between mb-5 gap-2">
          <h2 className="text-lg font-semibold text-text-primary tracking-tight">Evaluate Lines</h2>
          {hasOdds && !oddsLoading && (
            <span className="flex items-center gap-1 px-2 py-1 rounded-md bg-accent/10 text-accent text-[11px] font-medium flex-shrink-0">
              <Zap className="w-3 h-3" />
              <span className="hidden sm:inline">Lines auto-filled from</span> live odds
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
          {STATS.map(stat => {
            const hasLiveOdd = hasOdds && typeof odds?.[stat as keyof typeof odds] === 'number'
            return (
              <div key={stat}>
                <label className="flex items-center gap-1.5 text-xs font-medium text-text-muted mb-2 uppercase tracking-wider">
                  {stat}
                  {hasLiveOdd && <span className="text-accent normal-case font-normal tracking-normal">· live</span>}
                </label>
                <input
                  type="number"
                  step="0.5"
                  min="0.5"
                  value={lineInputs[stat] ?? ''}
                  onChange={e => {
                    const val = e.target.value
                    if (val === '' || parseFloat(val) > 0) {
                      setLineInputs(prev => ({ ...prev, [stat]: val }))
                    }
                  }}
                  placeholder="—"
                  className="w-full"
                />
              </div>
            )
          })}
        </div>

        <motion.button
          onClick={handleEvaluateAll}
          disabled={!hasAnyLine || isEvaluatingAll}
          className="btn btn-primary w-full ripple"
          whileTap={{ scale: 0.98 }}
          transition={{ duration: 0.1 }}
        >
          {isEvaluatingAll ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Evaluating…
            </>
          ) : (
            <>
              <PlaySquare className="w-4 h-4" />
              Evaluate All Lines
            </>
          )}
        </motion.button>

        <AnimatePresence>
          {allEvaluations.length > 0 && (
            <motion.div
              className="mt-6 space-y-4"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: 'easeOut' }}
            >
              {allEvaluations.map((ev, i) => (
                <motion.div
                  key={ev.stat}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.08, duration: 0.28, ease: 'easeOut' }}
                >
                  <EvalResult
                    evaluation={ev}
                    playerName={result.player_name}
                    onSave={buildSavePick(ev)}
                  />
                </motion.div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.section>
    </div>
  )
}

function InjuryColumn({ info, label }: { info: TeamInjuryInfo; label: string }) {
  const hasAny = info.out.length > 0 || info.questionable.length > 0
  if (!hasAny) return null

  return (
    <div>
      <div className="text-[11px] text-text-muted mb-1.5">
        <span className="font-medium text-text-secondary">{info.abbrev}</span>
        <span className="ml-1 text-text-muted">· {label}</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {info.out.map(p => (
          <span
            key={p.name}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-500/10 border border-red-500/20 text-red-400 text-[11px] font-medium"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-red-400 flex-shrink-0" />
            {p.name}
          </span>
        ))}
        {info.questionable.map(p => (
          <span
            key={p.name}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-yellow-500/10 border border-yellow-500/20 text-yellow-400 text-[11px] font-medium"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 flex-shrink-0" />
            {p.name}
          </span>
        ))}
      </div>
    </div>
  )
}

function EvalResult({
  evaluation,
  onSave,
}: {
  evaluation: LineEvaluation
  playerName: string
  onSave: () => Promise<void>
}) {
  const [isSaving, setIsSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const isOver = evaluation.recommendation.includes('OVER')

  const handleSave = async () => {
    setIsSaving(true)
    setSaveMessage(null)
    try {
      await onSave()
      setSaveMessage('Saved! Appears in Parlay Builder.')
      setTimeout(() => setSaveMessage(null), 4000)
    } catch {
      setSaveMessage('Failed to save pick')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className={`p-4 sm:p-5 rounded-xl border-y border-r ${isOver ? 'border-accent-success/20 bg-accent-success/[0.04] border-l-4 border-l-accent-success' : 'border-accent-danger/20 bg-accent-danger/[0.04] border-l-4 border-l-accent-danger'}`}>
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 sm:gap-5">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-3 sm:mb-4 flex-wrap">
            <div className={`pill ${isOver ? 'pill-over' : 'pill-under'}`}>{evaluation.recommendation}</div>
            <span className="text-xs text-text-muted font-mono">{evaluation.stat}</span>
            {evaluation.high_edge_warning && (
              <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-yellow-500/15 text-yellow-400 border border-yellow-500/20">
                High Edge — Verify
              </span>
            )}
          </div>
          <div className="grid grid-cols-3 gap-3 sm:gap-6">
            <div>
              <div className="text-[10px] sm:text-[11px] text-text-muted uppercase tracking-wider mb-1">Line</div>
              <div className="font-mono text-lg sm:text-xl font-bold text-text-primary">{evaluation.line}</div>
            </div>
            <div>
              <div className="text-[10px] sm:text-[11px] text-text-muted uppercase tracking-wider mb-1">Pred</div>
              <div className={`font-mono text-lg sm:text-xl font-bold ${isOver ? 'text-accent-success' : 'text-accent-danger'}`}>
                {evaluation.prediction.toFixed(1)}
              </div>
            </div>
            <div>
              <div className="text-[10px] sm:text-[11px] text-text-muted uppercase tracking-wider mb-1">Edge</div>
              <div className={`font-mono text-lg sm:text-xl font-bold ${Math.abs(evaluation.diff_pct) >= 8 ? 'text-accent' : 'text-text-primary'}`}>
                {evaluation.diff_pct > 0 ? '+' : ''}{evaluation.diff_pct.toFixed(1)}%
              </div>
            </div>
          </div>

          {evaluation.prob_over !== null && evaluation.prob_over !== undefined && (
            <div className="mt-5">
              <div className="flex items-center justify-between text-xs mb-2">
                <span className="text-accent-danger">Under</span>
                <span className="text-text-muted">{evaluation.prob_over.toFixed(0)}% Over</span>
                <span className="text-accent-success">Over</span>
              </div>
              <div className="h-1.5 bg-accent-danger/15 rounded-full overflow-hidden">
                <motion.div
                  className="h-full bg-accent-success rounded-full"
                  initial={{ width: 0 }}
                  animate={{ width: `${evaluation.prob_over}%` }}
                  transition={{ duration: 0.6, ease: 'easeOut', delay: 0.2 }}
                />
              </div>
            </div>
          )}
        </div>

        <div className="flex flex-col sm:items-end gap-2">
          <motion.button
            onClick={handleSave}
            disabled={isSaving}
            className={`btn ${isOver ? 'btn-over' : 'btn-under'} w-full sm:w-auto ripple`}
            whileTap={{ scale: 0.97 }}
            transition={{ duration: 0.1 }}
          >
            {isSaving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Check className="w-4 h-4" />
                Save Pick
              </>
            )}
          </motion.button>
          {saveMessage && (
            <span className={`text-xs text-right max-w-[160px] leading-snug ${saveMessage.includes('Saved') ? 'text-accent-success' : 'text-accent-danger'}`}>
              {saveMessage}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

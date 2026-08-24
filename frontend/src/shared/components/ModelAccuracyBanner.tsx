import { AlertTriangle } from 'lucide-react'

/**
 * The single source of truth for the model-accuracy disclosure.
 *
 * Every surface restored by `VITE_ENABLE_PREDICTIONS` renders this copy. Do not
 * fork or soften the wording — the numbers come from the 2026-08-23 audit
 * (`docs/SUMMARY_model_investigation_2026-08-23.md`).
 */
export const MODEL_ACCURACY_NOTICE =
  'Experimental model output. Measured record: 40-66 (37.7%) on 106 graded picks ' +
  'against real lines, versus a 52.4% breakeven. This model loses to a 10-game ' +
  'rolling average on every stat. Not a betting recommendation.'

/**
 * The ELO game predictor's own disclosure. Separate numbers, same rule: every
 * restored game-prediction surface renders this and nothing softer.
 * "24 correct of 38" is spelled out because "24-38" reads as a losing W-L record.
 */
export const GAME_MODEL_ACCURACY_NOTICE =
  'Experimental model output. Measured record: 24 correct of 38 graded playoff ' +
  'games (63.2%), against 55.3% for simply always picking the home team — a ' +
  'difference this sample cannot distinguish (p = 0.63). Brier score 0.2542, ' +
  'worse than predicting a constant 55.3%. Not a betting recommendation.'

interface ModelAccuracyBannerProps {
  /** Extra layout classes for the surface hosting the banner. */
  className?: string
  /** Which disclosure to show. Defaults to the per-player prop model's. */
  notice?: string
}

/**
 * Non-dismissible accuracy disclosure. Rendered on every prediction surface
 * that `VITE_ENABLE_PREDICTIONS` restores. There is deliberately no close
 * affordance and no persisted "seen" state.
 */
export default function ModelAccuracyBanner({
  className = '',
  notice = MODEL_ACCURACY_NOTICE,
}: ModelAccuracyBannerProps) {
  return (
    <div
      role="alert"
      data-testid="model-accuracy-banner"
      className={`flex items-start gap-3 rounded-xl border p-4 ${className}`}
      style={{
        borderColor: 'var(--accent-warning)',
        background: 'rgba(var(--warning-rgb), 0.10)',
      }}
    >
      <AlertTriangle
        className="w-4 h-4 flex-shrink-0 mt-0.5"
        style={{ color: 'var(--accent-warning)' }}
        aria-hidden="true"
      />
      <p
        className="text-xs leading-relaxed font-medium"
        style={{ color: 'var(--text-primary)' }}
      >
        {notice}
      </p>
    </div>
  )
}

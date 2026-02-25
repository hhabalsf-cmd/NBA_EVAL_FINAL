
/* ─── Shared SVG defs (glow filter + text arcs) ─── */
const BadgeDefs = () => (
  <defs>
    <filter id="bj-glow" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="2.5" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>
    <filter id="bj-glow-sm" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="1.5" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>
    {/* Top arc for "BETTIN'" text */}
    <path
      id="bj-top-arc"
      d="M 12,50 A 38,38 0 0,1 88,50"
      fill="none"
    />
    {/* Bottom arc for "JRYS" text */}
    <path
      id="bj-bot-arc"
      d="M 16,54 A 36,36 0 0,0 84,54"
      fill="none"
    />
  </defs>
)

/* ─── Basketball centre mark (reused by both variants) ─── */
interface MarkProps {
  cx?: number
  cy?: number
  r?: number
  gavelScale?: number
}

const BasketballGavelMark = ({ cx = 50, cy = 49, r = 19, gavelScale = 1 }: MarkProps) => {
  const gs = gavelScale
  return (
    <g>
      {/* Basketball */}
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill="none"
        stroke="#F59E0B"
        strokeWidth={2}
      />
      {/* Vertical seam */}
      <line
        x1={cx}
        y1={cy - r}
        x2={cx}
        y2={cy + r}
        stroke="#F59E0B"
        strokeWidth={1.5}
      />
      {/* Upper curved seam */}
      <path
        d={`M${cx - r},${cy} Q${cx},${cy - r * 0.68} ${cx + r},${cy}`}
        fill="none"
        stroke="#F59E0B"
        strokeWidth={1.5}
      />
      {/* Lower curved seam */}
      <path
        d={`M${cx - r},${cy} Q${cx},${cy + r * 0.68} ${cx + r},${cy}`}
        fill="none"
        stroke="#F59E0B"
        strokeWidth={1.5}
      />

      {/* ── Gavel (angled ~-42°, striking from top-right) ── */}
      {/* Gavel head */}
      <rect
        x={cx + 11 * gs}
        y={cy - 26 * gs}
        width={17 * gs}
        height={7 * gs}
        rx={2}
        fill="#06B6D4"
        transform={`rotate(-42 ${cx + 11 * gs + (17 * gs) / 2} ${cy - 26 * gs + (7 * gs) / 2})`}
      />
      {/* Gavel handle */}
      <line
        x1={cx + 10 * gs}
        y1={cy - 19 * gs}
        x2={cx - 13 * gs}
        y2={cy + 5 * gs}
        stroke="#06B6D4"
        strokeWidth={2.5 * gs}
        strokeLinecap="round"
      />
      {/* Gavel butt cap */}
      <rect
        x={cx - 17 * gs}
        y={cy + 2 * gs}
        width={8 * gs}
        height={5 * gs}
        rx={1.5}
        fill="#06B6D4"
        transform={`rotate(-42 ${cx - 17 * gs + (8 * gs) / 2} ${cy + 2 * gs + (7 * gs) / 2})`}
      />

      {/* ── Impact sparkles ── */}
      {/* Top-right cyan */}
      <line
        x1={cx + 14 * gs}
        y1={cy - 22 * gs}
        x2={cx + 18 * gs}
        y2={cy - 26 * gs}
        stroke="#06B6D4"
        strokeWidth={1.5 * gs}
        strokeLinecap="round"
        opacity={0.85}
      />
      {/* Right amber */}
      <line
        x1={cx + 17 * gs}
        y1={cy - 18 * gs}
        x2={cx + 21 * gs}
        y2={cy - 17 * gs}
        stroke="#F59E0B"
        strokeWidth={1.5 * gs}
        strokeLinecap="round"
        opacity={0.7}
      />
      {/* Top cyan (smaller) */}
      <line
        x1={cx + 10 * gs}
        y1={cy - 25 * gs}
        x2={cx + 11 * gs}
        y2={cy - 30 * gs}
        stroke="#06B6D4"
        strokeWidth={1 * gs}
        strokeLinecap="round"
        opacity={0.55}
      />
    </g>
  )
}

/* ─── Diamond separator ─── */
const Diamond = ({ cx, cy, size = 3 }: { cx: number; cy: number; size?: number }) => (
  <polygon
    points={`${cx},${cy - size} ${cx + size},${cy} ${cx},${cy + size} ${cx - size},${cy}`}
    fill="#F59E0B"
  />
)

/* ══════════════════════════════════════════
   LogoBadge — full circular badge
   ══════════════════════════════════════════ */
interface LogoBadgeProps {
  size?: number
  className?: string
}

export const LogoBadge = ({ size = 120, className = '' }: LogoBadgeProps) => (
  <div
    className={className}
    style={{
      display: 'inline-block',
      transition: 'transform 0.6s ease',
      transformStyle: 'preserve-3d',
    }}
    onMouseEnter={(e) => {
      ;(e.currentTarget as HTMLDivElement).style.transform = 'rotateY(360deg)'
    }}
    onMouseLeave={(e) => {
      ;(e.currentTarget as HTMLDivElement).style.transform = 'rotateY(0deg)'
    }}
  >
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="Bettin' Jrys logo"
      role="img"
    >
      <BadgeDefs />

      {/* Outer ring — glowing */}
      <circle
        cx="50"
        cy="50"
        r="48"
        fill="#09090B"
        stroke="#06B6D4"
        strokeWidth="2"
        filter="url(#bj-glow)"
        style={{
          animation: 'bj-ring-pulse 3s ease-in-out infinite',
        }}
      />

      {/* Inner decorative ring */}
      <circle
        cx="50"
        cy="50"
        r="42.5"
        fill="none"
        stroke="#06B6D4"
        strokeWidth="0.5"
        strokeOpacity="0.4"
      />

      {/* Tick marks every 30° on the inner ring */}
      {Array.from({ length: 12 }).map((_, i) => {
        const angle = (i * 30 * Math.PI) / 180
        const x1 = 50 + 42.5 * Math.cos(angle - Math.PI / 2)
        const y1 = 50 + 42.5 * Math.sin(angle - Math.PI / 2)
        const x2 = 50 + 40 * Math.cos(angle - Math.PI / 2)
        const y2 = 50 + 40 * Math.sin(angle - Math.PI / 2)
        return (
          <line
            key={i}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke="#06B6D4"
            strokeWidth={i % 3 === 0 ? 1 : 0.5}
            strokeOpacity={i % 3 === 0 ? 0.7 : 0.35}
          />
        )
      })}

      {/* "BETTIN'" arched on top */}
      <text
        fontFamily="'Bebas Neue', 'Inter', sans-serif"
        fontSize="10"
        fill="#06B6D4"
        letterSpacing="3.5"
      >
        <textPath href="#bj-top-arc" startOffset="50%" textAnchor="middle">
          BETTIN&apos;
        </textPath>
      </text>

      {/* "JRYS" arched on bottom */}
      <text
        fontFamily="'Bebas Neue', 'Inter', sans-serif"
        fontSize="10"
        fill="#06B6D4"
        letterSpacing="6"
      >
        <textPath href="#bj-bot-arc" startOffset="50%" textAnchor="middle">
          JRYS
        </textPath>
      </text>

      {/* Diamond separators at 9-o'clock and 3-o'clock */}
      <Diamond cx={8} cy={50} size={3.5} />
      <Diamond cx={92} cy={50} size={3.5} />

      {/* Basketball + Gavel centre mark */}
      <BasketballGavelMark cx={50} cy={49} r={19} gavelScale={1} />
    </svg>

    <style>{`
      @keyframes bj-ring-pulse {
        0%, 100% { filter: drop-shadow(0 0 3px #06B6D4) drop-shadow(0 0 6px rgba(6,182,212,0.35)); }
        50%       { filter: drop-shadow(0 0 6px #06B6D4) drop-shadow(0 0 14px rgba(6,182,212,0.55)); }
      }
    `}</style>
  </div>
)

/* ══════════════════════════════════════════
   LogoNav — compact nav-bar version
   ══════════════════════════════════════════ */
interface LogoNavProps {
  className?: string
}

export const LogoNav = ({ className = '' }: LogoNavProps) => (
  <div
    className={`flex items-center gap-2 group ${className}`}
    style={{ cursor: 'pointer' }}
  >
    {/* Small badge mark — no text ring, just the icon */}
    <div
      style={{
        transition: 'transform 0.25s ease, filter 0.25s ease',
      }}
      className="group-hover:[filter:drop-shadow(0_0_6px_#06B6D4)] group-hover:scale-110"
    >
      <svg
        width="32"
        height="32"
        viewBox="0 0 100 100"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <defs>
          <filter id="bj-nav-glow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Outer ring */}
        <circle
          cx="50"
          cy="50"
          r="47"
          fill="#09090B"
          stroke="#06B6D4"
          strokeWidth="2.5"
        />
        {/* Inner ring */}
        <circle
          cx="50"
          cy="50"
          r="41"
          fill="none"
          stroke="#06B6D4"
          strokeWidth="0.75"
          strokeOpacity="0.4"
        />

        {/* Centre mark — basketball + gavel, same as badge */}
        <BasketballGavelMark cx={50} cy={50} r={20} gavelScale={1} />
      </svg>
    </div>

    {/* Wordmark */}
    <span
      style={{
        fontFamily: "'Inter', sans-serif",
        fontWeight: 800,
        fontSize: '15px',
        lineHeight: 1,
        letterSpacing: '-0.01em',
        color: 'var(--text-primary)',
        transition: 'color 0.15s ease',
        userSelect: 'none',
      }}
      className="group-hover:text-accent"
    >
      Bettin&apos;{' '}
      <span
        style={{
          fontFamily: "'Bebas Neue', sans-serif",
          fontWeight: 400,
          fontSize: '16px',
          letterSpacing: '0.04em',
          color: 'var(--accent)',
        }}
      >
        Jrys
      </span>
    </span>
  </div>
)

export default LogoBadge

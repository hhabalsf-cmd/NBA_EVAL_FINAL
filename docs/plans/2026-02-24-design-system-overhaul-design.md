# Design System Overhaul — NBA EVAL Frontend
**Date:** 2026-02-24
**Approach:** Design System First (cascading token → component → page)
**Direction:** Data Dashboard / Pro Analytics (Bloomberg/Statcast terminal aesthetic)

---

## Context

The NBA EVAL frontend has a solid dark theme foundation with a warm gold accent (`#C9A87C`), but the visual system lacks punch and consistency. Cards are flat, confidence bars are thin, buttons are plain, and repeated patterns like section labels exist as inline Tailwind strings rather than utility classes. The goal is to upgrade the design to a premium analytics dashboard feel — sharper numbers, more elevated surfaces, better visual hierarchy — while keeping full consistency across all pages and both light/dark themes.

The previous "experimental" tab in ResearchPage was the benchmark for quality; this overhaul brings the rest of the app up to that standard.

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Accent color | `#E8A430` (bright amber) | Higher contrast (7.2:1), more vivid analytics feel vs. muted current gold |
| Approach | Design-system-first | Token changes cascade to all pages automatically; minimal React refactoring |
| Card elevation | Box shadow by default | Makes cards feel elevated vs. flat; subtle but impactful |
| Confidence bars | 8px height + gradient | More visible data signal; grad shows quality at a glance |
| Button style | Gradient + lift on hover | Premium interactive feel without being garish |
| Typography | New CSS utility classes | Eliminate 30+ instances of repeated `text-[11px] uppercase tracking-wider` |

---

## Changes by Layer

### Layer 1: CSS Variables (`frontend/src/index.css`)

#### Color Token Updates
```css
/* BEFORE */
--accent: #C9A87C;
--accent-hover: #B8956A;

/* AFTER */
--accent: #E8A430;
--accent-hover: #CC8F15;
--accent-muted: rgba(232, 164, 48, 0.12);
--accent-glow: rgba(232, 164, 48, 0.15);   /* NEW — card top-border glow */
--border-accent: rgba(232, 164, 48, 0.25); /* NEW — accent card borders */
```

#### New Shadow Scale
```css
--shadow-sm: 0 1px 4px rgba(0, 0, 0, 0.2);
--shadow-md: 0 4px 16px rgba(0, 0, 0, 0.3);
--shadow-lg: 0 8px 32px rgba(0, 0, 0, 0.4);
```

#### Light Theme Updates
```css
:root.light {
  --accent: #B5710D;           /* darker amber on white background */
  --accent-hover: #9A5E08;
  --accent-muted: rgba(181, 113, 13, 0.1);
  --accent-glow: rgba(181, 113, 13, 0.12);
  --border-accent: rgba(181, 113, 13, 0.2);
  --shadow-sm: 0 1px 4px rgba(0, 0, 0, 0.06);
  --shadow-md: 0 4px 16px rgba(0, 0, 0, 0.10);
  --shadow-lg: 0 8px 32px rgba(0, 0, 0, 0.14);
}
```

### Layer 2: CSS Utility Classes (`frontend/src/index.css`)

#### Card Improvements
```css
/* Add default shadow + new variant */
.card {
  box-shadow: var(--shadow-sm);   /* ADD — was missing */
}
.card-hover:hover {
  transform: translateY(-1px);    /* ADD — lift effect */
  box-shadow: var(--shadow-md);   /* IMPROVE — from --shadow-card */
}
/* NEW VARIANT — accent top border for stat/prediction cards */
.card-accent {
  border-top: 2px solid var(--accent);
}
```

#### Button Polish
```css
.btn-primary {
  background: linear-gradient(135deg, var(--accent) 0%, var(--accent-hover) 100%);
  /* REPLACE flat background */
}
.btn:hover:not(:disabled) {
  transform: translateY(-1px);  /* ADD — lift on hover */
}
.btn {
  transition: background 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
  /* STANDARDIZE transition */
}
```

#### New Typography Utilities
```css
/* Replaces 30+ instances of repeated inline Tailwind strings */
.label-xs {
  font-size: 0.625rem;    /* 10px */
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  font-weight: 600;
}
.stat-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1.5rem;     /* 24px */
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text-primary);
}
.section-header {
  font-size: 0.625rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  font-weight: 600;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--border-subtle);
  margin-bottom: 0.75rem;
}
```

#### Confidence Bar Update
```css
.confidence-fill {
  height: 6px;   /* INCREASE from 4px */
  border-radius: 9999px;
  /* gradient fill added inline via JS (color is dynamic based on value) */
}
.progress-fill {
  height: 4px;   /* INCREASE from 3px */
  border-radius: 9999px;
}
```

### Layer 3: Page-Specific Changes

#### `frontend/src/pages/PlayerPage.tsx`
- Add `card-accent` class to each of the 4 stat prediction cards (PTS/REB/AST/PRA)
- Update confidence bar height to 8px (inline style or via new class)
- Line evaluation results: add `border-l-2 border-l-accent` left accent bar

#### `frontend/src/pages/HomePage.tsx`
- Performance stats strip: wrap each metric (Win Rate, ROI, Record) in a `.card` with larger JetBrains Mono number display
- Stat breakdown cards: add `.card-accent` class

#### `frontend/src/pages/LandingPage.tsx`
- Hero heading: increase to `text-4xl sm:text-5xl lg:text-6xl`, tighter tracking `-tracking-tight`
- Stats strip: use `.stat-value` class for the big numbers

#### `frontend/src/pages/GamesPage.tsx`
- Win probability bars: add gradient fill `linear-gradient(90deg, var(--accent) 0%, var(--accent-hover) 100%)`
- Key factors section header: use `.section-header` class

#### `frontend/tailwind.config.js`
- Expose new CSS variables: `accent-glow`, `border-accent`, `shadow-sm`, `shadow-md`, `shadow-lg` as Tailwind tokens

---

## Files to Modify

| File | Change Type |
|------|-------------|
| `frontend/src/index.css` | Color tokens, shadow scale, card/button/typography utilities |
| `frontend/tailwind.config.js` | Expose new CSS var tokens |
| `frontend/src/pages/PlayerPage.tsx` | card-accent, confidence bars, line eval border |
| `frontend/src/pages/HomePage.tsx` | Performance stats card grid, stat card accents |
| `frontend/src/pages/LandingPage.tsx` | Hero typography, stats strip |
| `frontend/src/pages/GamesPage.tsx` | Probability bar gradient, section headers |
| `frontend/src/pages/HistoryPage.tsx` | Table header improvements, section-header class |
| `frontend/src/pages/ParlayPage.tsx` | Section headers, card-accent on parlay legs |

---

## Verification

1. Run `cd frontend && npm run dev` — check all pages visually in both dark and light themes
2. Verify accent color updates propagate across all pages (search for old `#C9A87C` hardcoded values)
3. Check PlayerPage stat cards have amber top border
4. Check buttons have gradient + lift on hover
5. Check confidence bars are taller (8px)
6. Run `npm run lint` — no TypeScript/ESLint errors
7. Run `npm run build` — production build succeeds

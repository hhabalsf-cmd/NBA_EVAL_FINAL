# TikTok Top 5 Picks Video — Design Doc

**Date:** 2026-02-27
**Status:** Approved

## Goal

Generate a 9:16 vertical MP4 video (TikTok-ready) showing the top 5 NBA prop picks for tonight, using Remotion. Standalone project in `/video` — no impact on existing frontend.

## Picks (2026-02-27)

| Rank | Player | Team | Stat | Direction | Line | Hit Prob |
|------|--------|------|------|-----------|------|----------|
| 1 | Cason Wallace | OKC | PRA | OVER | 14.5 | 85% |
| 2 | Jaylen Brown | BOS | REB | OVER | 6.5 | 80% |
| 3 | Jamal Murray | DEN | REB | OVER | 3.5 | 74% |
| 4 | Derrick White | BOS | REB | OVER | 3.5 | 73% |
| 5 | Tobias Harris | DET | REB | OVER | 5.5 | 73% |

## Video Specs

- **Resolution:** 1080×1920 (9:16 vertical, TikTok native)
- **FPS:** 30
- **Duration:** ~20 seconds total
- **Output:** `video/out/top5-picks.mp4`

## Scene Structure

### Scene 1 — Intro (2s, frames 0–60)
- Black background fades in
- "TOP 5 PLAYS" text animates in from below (spring)
- "TONIGHT · FEB 27" subtitle fades in

### Scenes 2–6 — Pick Slides (3s each = 15s, frames 60–510)
Each pick gets its own scene:
- Slide number badge (#5 → #1) in gold
- Player name (large, bold white)
- Team abbreviation · Stat label (muted gold)
- "OVER [line]" pill (green)
- Hit probability bar: fills from 0% to final value on entry
- Card slides up with spring physics on entry

### Scene 7 — Outro (1s, frames 510–540)
- "FOLLOW FOR MORE PICKS" text flash
- Brief logo/brand mark

## Visual Language

| Token | Value |
|-------|-------|
| Background | `#09090B` |
| Card background | `#131316` |
| Accent gold | `#C9A87C` |
| Success green | `#6BBF8A` |
| Text primary | `#EDEDEC` |
| Text muted | `#8F8B87` |
| Font | Inter (Google Fonts CDN) |
| Number font | JetBrains Mono |

## Project Structure

```
video/
  package.json          # Remotion deps only
  remotion.config.ts    # Composition config
  src/
    Root.tsx            # registerRoot, composition registration
    compositions/
      Top5Picks.tsx     # Main composition (wraps all scenes)
    scenes/
      Intro.tsx
      PickSlide.tsx     # Parameterized per pick
      Outro.tsx
    data/
      picks.ts          # Today's picks data
    utils/
      animations.ts     # Spring helpers
```

## Build & Render

```bash
cd video
npm install
npx remotion render Top5Picks out/top5-picks.mp4
```

## Future Reuse

To update picks: edit `src/data/picks.ts` and re-run render. No code changes needed.

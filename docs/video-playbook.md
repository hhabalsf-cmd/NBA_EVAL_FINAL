# TikTok Video Playbook

Reference for generating and formatting NBA prediction videos with Remotion + ElevenLabs.

---

## Project Structure

```
video/
├── src/
│   ├── data/picks.ts              ← Edit this to update picks
│   ├── scenes/
│   │   ├── Intro.tsx              ← 2s opening scene
│   │   ├── PickSlide.tsx          ← Per-pick scene (rendered 5×)
│   │   └── Outro.tsx              ← 1s closing scene
│   ├── compositions/Top5Picks.tsx ← Wires all scenes with TransitionSeries
│   ├── Root.tsx                   ← Remotion composition config
│   └── index.ts                   ← Entry point
├── public/audio/                  ← ElevenLabs MP3s (7 files)
├── generate_audio.py              ← Generates voiceover MP3s
├── out/top5-picks.mp4             ← Final rendered video
└── package.json
```

---

## Duration

| Scene | Frames | Seconds |
|-------|--------|---------|
| Intro | 60 | 2s |
| Pick × 5 | 90 each = 450 | 15s |
| Outro | 30 | 1s |
| 6 slide transitions × 15 frames | −90 | −3s |
| **Total** | **450** | **15s** |

FPS: 30 · Format: 1080×1920 (9:16 TikTok vertical) · Codec: H.264

---

## Updating Picks

Edit `video/src/data/picks.ts`:

```ts
export const PICKS: Pick[] = [
  {
    rank: 1,           // 1–5, shown as #N badge
    player: "Name",   // Full name — large headline text
    team: "OKC",      // 3-letter abbreviation
    stat: "PRA",      // PTS / REB / AST / PRA
    direction: "OVER", // "OVER" or "UNDER" — renders as ↑ or ↓
    line: 14.5,       // The stat line
    hitProb: 85,      // 0–100, drives the confidence bar
  },
  // ...
];

export const DATE_LABEL = "FEB 27, 2026"; // Shown on Intro scene
```

Then render:

```bash
cd video && npm run render
```

---

## Render Commands

```bash
cd video

# Full render → out/top5-picks.mp4
npm run render

# Still frame for thumbnail
npm run render:still   # frame 90 by default

# Preview in browser
npm start
```

---

## Voiceover (ElevenLabs)

Voice: **Daniel** (`onwK4e9ZLuTAKqWW03F9`) — male, authoritative
Model: `eleven_multilingual_v2`
Settings: stability 0.55, similarity 0.80, speed 1.05

**Punchy script format:**
- Intro: `"Tonight's top 5 NBA predictions."`
- Pick: `"Number {rank}. {Player}, {direction-word} {line} {stat-full}."`
  - e.g. `"Number one. Cason Wallace, above 14.5 PRA."`
- Outro: `"Follow for daily predictions."`

**Generate audio:**
```bash
ELEVENLABS_API_KEY=your_key python3 video/generate_audio.py
```

Then update `SCRIPTS` dict in `generate_audio.py` to match new picks before running.

**Audio timing fix:** Each `<Audio>` must be wrapped in `<Sequence from={15}>` to prevent overlap during the 15-frame slide transitions:
```tsx
<Sequence from={15}>
  <Audio src={staticFile("audio/pick-1.mp3")} />
</Sequence>
```

---

## TikTok Compliance Rules

TikTok flags explicit gambling/betting language. Always use neutral framing:

| ❌ Flagged | ✅ Safe |
|-----------|--------|
| OVER / UNDER | ↑ / ↓ |
| Hit Probability | Confidence |
| TOP 5 PLAYS | TOP 5 PREDICTIONS |
| "picks" | "predictions" |
| "prop bet" | "stat prediction" |
| "line" (in captions) | "projection" |

---

## Caption Template

```
My model just locked in tonight's top 5 NBA predictions 🏀📊

Drop a ✅ if you want tomorrow's too

#NBA #NBATwitter #NBApicks #basketball #sportspredictions #nbahighlights #hoops #nba2025 #sportsbrain #nbadaily
```

**Caption rules:**
- Open with a hook about the model/algorithm (credibility)
- Ask for a comment reaction (drives TikTok distribution)
- 8–10 hashtags: mix broad (`#NBA`, `#basketball`) + niche (`#sportspredictions`, `#nbadaily`)
- Never use: `#betting`, `#sportsbetting`, `#props`, `#prizepicks`, `#gambling`

---

## Theme / Design Tokens

| Token | Value | Used for |
|-------|-------|---------|
| `BG` | `#09090B` | Background |
| `CARD_BG` | `#131316` | Pick card background |
| `GOLD` | `#C9A87C` | Accent, rank badge, team name |
| `WHITE` | `#EDEDEC` | Primary text |
| `MUTED` | `#8F8B87` | Secondary text |
| `GREEN` | `#6BBF8A` | Direction pill, confidence bar |
| `BORDER` | `#232329` | Card border, bar track |

Font: **Inter** (Google Fonts via `@remotion/google-fonts/Inter`)

---

## Full Update Workflow (New Night)

1. Update `video/src/data/picks.ts` — new players, lines, hitProbs, DATE_LABEL
2. Update `SCRIPTS` in `video/generate_audio.py` — match new picks
3. `ELEVENLABS_API_KEY=your_key python3 video/generate_audio.py`
4. `cd video && npm run render`
5. Post `video/out/top5-picks.mp4` with caption from template above

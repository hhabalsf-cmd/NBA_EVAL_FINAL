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
| Pick × N | 120 each | 4s each |
| Outro | 30 | 1s |
| (N+1) slide transitions × 15 | −15×(N+1) | varies |
| **Total (4 picks)** | **495** | **~16.5s** |
| **Total (5 picks)** | **600** | **~20s** |

**Duration is auto-computed** — `TOTAL_FRAMES` in `Top5Picks.tsx` recalculates whenever you change the number of picks in `picks.ts`. Never update `Root.tsx` manually.

FPS: 30 · Format: 1080×1920 (9:16 TikTok vertical) · Codec: H.264

---

## Updating Picks

Edit `video/src/data/picks.ts`:

```ts
export const PICKS: Pick[] = [
  {
    rank: 1,              // 1–N, shown as #N badge
    player: "Name",      // Full name — large headline text
    team: "OKC",         // 3-letter abbreviation
    stat: "PRA",         // PTS / REB / AST / PRA / PA / PR
    direction: "OVER",   // "OVER" or "UNDER" — renders as ↑ or ↓
    line: 14.5,          // The stat line
    hitProb: 85,         // 0–100, drives the confidence bar + count-up
    opponent: "vs. WAS · Weak DEF", // optional — shown below team row
  },
  // ...
];

// DATE_LABEL is now auto-computed from new Date() — no manual update needed
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

### Structure: Hook → Picks → CTA → Hashtags

**Hook (pick one — curiosity gap drives retention):**
```
The numbers are too clean on this one 👀
{N} predictions. Can the model go {N}/{N}? 🤖
This matchup screams ↑ — here's why
AI locked in on these tonight. Let's see 📊
```

**Body (list picks):**
```
{Player} {stat} ↑ {line}
{Player} {stat} ↑ {line}
...
```

**CTA (active — comment CTAs 3× more valuable than follows):**
```
Drop a 🔥 if you're riding · Follow for daily predictions
Comment your lock below 👇
✅ if you're fading or 🔥 if you're riding
```

**Hashtags (5–8 max):**
```
#NBA #NBATonight #SportsTikTok #NBAStats #basketball
+ 1–2 player-specific: e.g. #KevindDurant #Suns
```

**Full example:**
```
The numbers are too clean on this one 👀

Kevin Durant PA ↑ 30.5
Bilal Coulibaly PRA ↑ 15.5
Kawhi Leonard PR ↑ 34.5
Brandin Podziemski PA ↑ 10.5

Drop a 🔥 if you're riding · Follow for daily predictions

#NBA #NBATonight #SportsTikTok #NBAStats #basketball #KevinDurant
```

**Caption rules:**
- Open with curiosity gap (not a generic statement) — first line is the hook
- Use ↑/↓ symbols in the body (never OVER/UNDER)
- Ask for a comment reaction (comments signal engagement to TikTok algorithm)
- 5–8 hashtags only — more than 10 hurts reach
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

1. Update `video/src/data/picks.ts` — new players, lines, hitProbs, opponent context
   - `DATE_LABEL` is auto-computed, skip it
   - `TOTAL_FRAMES` in Root.tsx is auto-computed from pick count, skip it
2. Update `SCRIPTS` in `video/generate_audio.py` — match new picks
3. `ELEVENLABS_API_KEY=your_key python3 video/generate_audio.py`
4. `cd video && npm run render`
5. Post `video/out/top5-picks.mp4` with caption from template above

# TikTok Top 5 Picks Video — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Render a 1080×1920 TikTok-ready MP4 showing tonight's top 5 NBA prop picks using a standalone Remotion project in `/video`.

**Architecture:** Standalone `video/` directory at project root — no impact on existing app. Uses `<TransitionSeries>` with slide transitions between scenes. Each pick is a parameterized `<PickSlide>` component driven entirely by `useCurrentFrame()`. Picks data lives in `src/data/picks.ts` so future updates require zero code changes.

**Tech Stack:** Remotion 4.x, `@remotion/transitions`, `@remotion/google-fonts` (Inter + JetBrains Mono), TypeScript, React 18

---

## Duration Math

| Scene | Frames | Seconds |
|-------|--------|---------|
| Intro | 60 | 2s |
| Pick × 5 | 90 each = 450 | 15s |
| Outro | 30 | 1s |
| **Raw total** | **540** | **18s** |
| 6 slide transitions × 15 frames | −90 | −3s |
| **Rendered total** | **450** | **15s** |

> Composition `durationInFrames = 450`.

---

## Task 1: Scaffold the Remotion project

**Files:**
- Create: `video/package.json`
- Create: `video/tsconfig.json`
- Create: `video/remotion.config.ts`

**Step 1: Create directory and package.json**

```bash
mkdir -p video
```

Create `video/package.json`:

```json
{
  "name": "nba-picks-video",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "start": "npx remotion studio",
    "render": "npx remotion render Top5Picks out/top5-picks.mp4",
    "render:still": "npx remotion still Top5Picks out/still.png --frame=90"
  },
  "dependencies": {
    "@remotion/cli": "4.0.290",
    "@remotion/google-fonts": "4.0.290",
    "@remotion/transitions": "4.0.290",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "remotion": "4.0.290"
  },
  "devDependencies": {
    "@types/react": "^18.3.1",
    "@types/react-dom": "^18.3.1",
    "typescript": "^5.4.5"
  }
}
```

**Step 2: Create tsconfig.json**

Create `video/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "ES2022"],
    "module": "commonjs",
    "jsx": "react",
    "strict": true,
    "moduleResolution": "node",
    "esModuleInterop": true,
    "skipLibCheck": true
  },
  "include": ["src"]
}
```

**Step 3: Create remotion.config.ts**

Create `video/remotion.config.ts`:

```ts
import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
```

**Step 4: Install dependencies**

```bash
cd video && npm install
```

Expected: `node_modules/` created, no errors.

**Step 5: Create output directory**

```bash
mkdir -p video/out
```

**Step 6: Commit**

```bash
git add video/package.json video/tsconfig.json video/remotion.config.ts
git commit -m "feat(video): scaffold Remotion project"
```

---

## Task 2: Create picks data file

**Files:**
- Create: `video/src/data/picks.ts`

**Step 1: Create data directory and picks file**

```bash
mkdir -p video/src/data
```

Create `video/src/data/picks.ts`:

```ts
export type Pick = {
  rank: number;
  player: string;
  team: string;
  stat: string;
  direction: "OVER" | "UNDER";
  line: number;
  hitProb: number; // 0–100
};

export const PICKS: Pick[] = [
  {
    rank: 1,
    player: "Cason Wallace",
    team: "OKC",
    stat: "PRA",
    direction: "OVER",
    line: 14.5,
    hitProb: 85,
  },
  {
    rank: 2,
    player: "Jaylen Brown",
    team: "BOS",
    stat: "REB",
    direction: "OVER",
    line: 6.5,
    hitProb: 80,
  },
  {
    rank: 3,
    player: "Jamal Murray",
    team: "DEN",
    stat: "REB",
    direction: "OVER",
    line: 3.5,
    hitProb: 74,
  },
  {
    rank: 4,
    player: "Derrick White",
    team: "BOS",
    stat: "REB",
    direction: "OVER",
    line: 3.5,
    hitProb: 73,
  },
  {
    rank: 5,
    player: "Tobias Harris",
    team: "DET",
    stat: "REB",
    direction: "OVER",
    line: 5.5,
    hitProb: 73,
  },
];

export const DATE_LABEL = "FEB 27, 2026";
```

**Step 2: Commit**

```bash
git add video/src/data/picks.ts
git commit -m "feat(video): add picks data"
```

---

## Task 3: Create Intro scene

**Files:**
- Create: `video/src/scenes/Intro.tsx`

**Step 1: Create scenes directory and Intro component**

```bash
mkdir -p video/src/scenes
```

Create `video/src/scenes/Intro.tsx`:

```tsx
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { loadFont } from "@remotion/google-fonts/Inter";

const { fontFamily } = loadFont("normal", {
  weights: ["700", "900"],
  subsets: ["latin"],
});

const GOLD = "#C9A87C";
const BG = "#09090B";
const WHITE = "#EDEDEC";
const MUTED = "#8F8B87";

export const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // "TOP 5 PLAYS" slides up and fades in
  const titleSpring = spring({
    frame,
    fps,
    config: { damping: 18, stiffness: 120 },
    durationInFrames: 30,
  });

  const titleY = interpolate(titleSpring, [0, 1], [60, 0]);
  const titleOpacity = interpolate(titleSpring, [0, 1], [0, 1]);

  // Subtitle fades in after title
  const subtitleOpacity = interpolate(frame, [20, 40], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  // Gold divider scales in
  const dividerScale = spring({
    frame: frame - 10,
    fps,
    config: { damping: 200 },
    durationInFrames: 25,
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: BG,
        justifyContent: "center",
        alignItems: "center",
        flexDirection: "column",
        gap: 16,
      }}
    >
      {/* Basketball emoji */}
      <div
        style={{
          fontSize: 80,
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
          marginBottom: 8,
        }}
      >
        🏀
      </div>

      {/* TOP 5 PLAYS */}
      <div
        style={{
          fontFamily,
          fontWeight: 900,
          fontSize: 88,
          color: WHITE,
          letterSpacing: -2,
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
          textAlign: "center",
          lineHeight: 1,
        }}
      >
        TOP 5 PLAYS
      </div>

      {/* Gold divider */}
      <div
        style={{
          width: interpolate(dividerScale, [0, 1], [0, 280]),
          height: 3,
          backgroundColor: GOLD,
          borderRadius: 2,
          margin: "8px 0",
        }}
      />

      {/* TONIGHT subtitle */}
      <div
        style={{
          fontFamily,
          fontWeight: 700,
          fontSize: 36,
          color: GOLD,
          letterSpacing: 8,
          opacity: subtitleOpacity,
        }}
      >
        TONIGHT
      </div>

      {/* Date */}
      <div
        style={{
          fontFamily,
          fontWeight: 400,
          fontSize: 24,
          color: MUTED,
          letterSpacing: 3,
          opacity: subtitleOpacity,
        }}
      >
        FEB 27, 2026
      </div>
    </AbsoluteFill>
  );
};
```

**Step 2: Commit**

```bash
git add video/src/scenes/Intro.tsx
git commit -m "feat(video): add Intro scene"
```

---

## Task 4: Create PickSlide scene

**Files:**
- Create: `video/src/scenes/PickSlide.tsx`

This is the core scene — rendered 5 times with different props.

**Step 1: Create PickSlide**

Create `video/src/scenes/PickSlide.tsx`:

```tsx
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { loadFont } from "@remotion/google-fonts/Inter";
import type { Pick } from "../data/picks";

const { fontFamily } = loadFont("normal", {
  weights: ["400", "700", "900"],
  subsets: ["latin"],
});

const GOLD = "#C9A87C";
const BG = "#09090B";
const CARD_BG = "#131316";
const WHITE = "#EDEDEC";
const MUTED = "#8F8B87";
const GREEN = "#6BBF8A";
const BORDER = "#232329";

export const PickSlide: React.FC<{ pick: Pick }> = ({ pick }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Card slides up on entry
  const cardSpring = spring({
    frame,
    fps,
    config: { damping: 18, stiffness: 120 },
    durationInFrames: 35,
  });
  const cardY = interpolate(cardSpring, [0, 1], [80, 0]);
  const cardOpacity = interpolate(cardSpring, [0, 1], [0, 1]);

  // Rank badge pops in
  const badgeSpring = spring({
    frame: frame - 5,
    fps,
    config: { damping: 12, stiffness: 200 },
    durationInFrames: 25,
  });
  const badgeScale = interpolate(badgeSpring, [0, 1], [0.5, 1]);

  // Hit prob bar fills in (starts at frame 20)
  const barProgress = interpolate(frame, [20, 55], [0, pick.hitProb / 100], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  // Player name fades in with slight delay
  const nameOpacity = interpolate(frame, [8, 22], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  const CARD_WIDTH = 860;
  const BAR_MAX_WIDTH = CARD_WIDTH - 80;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: BG,
        justifyContent: "center",
        alignItems: "center",
        flexDirection: "column",
        gap: 32,
      }}
    >
      {/* Rank badge */}
      <div
        style={{
          transform: `scale(${badgeScale})`,
          backgroundColor: GOLD,
          borderRadius: 50,
          width: 80,
          height: 80,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <span
          style={{
            fontFamily,
            fontWeight: 900,
            fontSize: 40,
            color: BG,
            lineHeight: 1,
          }}
        >
          #{pick.rank}
        </span>
      </div>

      {/* Main card */}
      <div
        style={{
          width: CARD_WIDTH,
          backgroundColor: CARD_BG,
          borderRadius: 24,
          border: `1px solid ${BORDER}`,
          padding: "48px 40px",
          transform: `translateY(${cardY}px)`,
          opacity: cardOpacity,
          display: "flex",
          flexDirection: "column",
          gap: 24,
        }}
      >
        {/* Player name */}
        <div
          style={{
            fontFamily,
            fontWeight: 900,
            fontSize: 72,
            color: WHITE,
            letterSpacing: -2,
            lineHeight: 1.05,
            opacity: nameOpacity,
          }}
        >
          {pick.player}
        </div>

        {/* Team · Stat row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            opacity: nameOpacity,
          }}
        >
          <span
            style={{
              fontFamily,
              fontWeight: 700,
              fontSize: 32,
              color: GOLD,
              letterSpacing: 1,
            }}
          >
            {pick.team}
          </span>
          <span style={{ color: MUTED, fontSize: 28 }}>·</span>
          <span
            style={{
              fontFamily,
              fontWeight: 700,
              fontSize: 32,
              color: MUTED,
              letterSpacing: 1,
            }}
          >
            {pick.stat}
          </span>
        </div>

        {/* OVER / UNDER pill + line */}
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div
            style={{
              backgroundColor: GREEN,
              borderRadius: 8,
              padding: "8px 20px",
              display: "inline-flex",
            }}
          >
            <span
              style={{
                fontFamily,
                fontWeight: 900,
                fontSize: 28,
                color: BG,
                letterSpacing: 2,
              }}
            >
              {pick.direction}
            </span>
          </div>
          <span
            style={{
              fontFamily,
              fontWeight: 900,
              fontSize: 52,
              color: WHITE,
              letterSpacing: -1,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {pick.line}
          </span>
        </div>

        {/* Hit prob bar */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span
              style={{
                fontFamily,
                fontSize: 22,
                color: MUTED,
                fontWeight: 400,
              }}
            >
              Hit Probability
            </span>
            <span
              style={{
                fontFamily,
                fontWeight: 700,
                fontSize: 26,
                color: GREEN,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {Math.round(barProgress * 100)}%
            </span>
          </div>

          {/* Track */}
          <div
            style={{
              width: BAR_MAX_WIDTH,
              height: 12,
              backgroundColor: BORDER,
              borderRadius: 6,
              overflow: "hidden",
            }}
          >
            {/* Fill */}
            <div
              style={{
                width: BAR_MAX_WIDTH * barProgress,
                height: "100%",
                backgroundColor: GREEN,
                borderRadius: 6,
              }}
            />
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
```

**Step 2: Commit**

```bash
git add video/src/scenes/PickSlide.tsx
git commit -m "feat(video): add PickSlide scene"
```

---

## Task 5: Create Outro scene

**Files:**
- Create: `video/src/scenes/Outro.tsx`

**Step 1: Create Outro**

Create `video/src/scenes/Outro.tsx`:

```tsx
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { loadFont } from "@remotion/google-fonts/Inter";

const { fontFamily } = loadFont("normal", {
  weights: ["700", "900"],
  subsets: ["latin"],
});

const GOLD = "#C9A87C";
const BG = "#09090B";
const WHITE = "#EDEDEC";

export const Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const spring1 = spring({
    frame,
    fps,
    config: { damping: 15, stiffness: 200 },
    durationInFrames: 20,
  });

  const scale = interpolate(spring1, [0, 1], [0.8, 1]);
  const opacity = interpolate(spring1, [0, 1], [0, 1]);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: BG,
        justifyContent: "center",
        alignItems: "center",
        flexDirection: "column",
        gap: 16,
      }}
    >
      <div
        style={{
          transform: `scale(${scale})`,
          opacity,
          textAlign: "center",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 16,
        }}
      >
        <div style={{ fontSize: 72 }}>🏀</div>
        <div
          style={{
            fontFamily,
            fontWeight: 900,
            fontSize: 56,
            color: WHITE,
            letterSpacing: -1,
            lineHeight: 1.1,
            textAlign: "center",
          }}
        >
          FOLLOW FOR MORE
          {"\n"}PICKS
        </div>
        <div
          style={{
            fontFamily,
            fontWeight: 700,
            fontSize: 28,
            color: GOLD,
            letterSpacing: 3,
            marginTop: 8,
          }}
        >
          DAILY NBA PROPS
        </div>
      </div>
    </AbsoluteFill>
  );
};
```

**Step 2: Commit**

```bash
git add video/src/scenes/Outro.tsx
git commit -m "feat(video): add Outro scene"
```

---

## Task 6: Create Top5Picks composition and Root

**Files:**
- Create: `video/src/compositions/Top5Picks.tsx`
- Create: `video/src/Root.tsx`
- Create: `video/src/index.ts`

**Step 1: Create composition**

```bash
mkdir -p video/src/compositions
```

Create `video/src/compositions/Top5Picks.tsx`:

```tsx
import { AbsoluteFill } from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { slide } from "@remotion/transitions/slide";
import { Intro } from "../scenes/Intro";
import { PickSlide } from "../scenes/PickSlide";
import { Outro } from "../scenes/Outro";
import { PICKS } from "../data/picks";

// Scene durations (frames at 30fps)
const INTRO_FRAMES = 60;    // 2s
const PICK_FRAMES = 90;     // 3s each
const OUTRO_FRAMES = 30;    // 1s
const TRANSITION_FRAMES = 15; // 0.5s

const transition = slide({ direction: "from-bottom" });
const timing = linearTiming({ durationInFrames: TRANSITION_FRAMES });

export const Top5Picks: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#09090B" }}>
      <TransitionSeries>
        {/* Intro */}
        <TransitionSeries.Sequence durationInFrames={INTRO_FRAMES}>
          <Intro />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={transition} timing={timing} />

        {/* Picks #1 → #5 (sorted rank 1 first = most exciting) */}
        {PICKS.map((pick, i) => (
          <>
            <TransitionSeries.Sequence
              key={pick.rank}
              durationInFrames={PICK_FRAMES}
            >
              <PickSlide pick={pick} />
            </TransitionSeries.Sequence>
            {i < PICKS.length - 1 && (
              <TransitionSeries.Transition
                key={`t-${pick.rank}`}
                presentation={transition}
                timing={timing}
              />
            )}
          </>
        ))}

        {/* Transition to outro */}
        <TransitionSeries.Transition presentation={transition} timing={timing} />

        {/* Outro */}
        <TransitionSeries.Sequence durationInFrames={OUTRO_FRAMES}>
          <Outro />
        </TransitionSeries.Sequence>
      </TransitionSeries>
    </AbsoluteFill>
  );
};
```

**Step 2: Create Root.tsx**

Create `video/src/Root.tsx`:

```tsx
import { Composition } from "remotion";
import { Top5Picks } from "./compositions/Top5Picks";

// Total: 60 + (90×5) + 30 - (15×6 transitions) = 450 frames
const DURATION = 450;

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Top5Picks"
      component={Top5Picks}
      durationInFrames={DURATION}
      fps={30}
      width={1080}
      height={1920}
    />
  );
};
```

**Step 3: Create index.ts entry point**

Create `video/src/index.ts`:

```ts
import { registerRoot } from "remotion";
import { RemotionRoot } from "./Root";

registerRoot(RemotionRoot);
```

**Step 4: Commit**

```bash
git add video/src/
git commit -m "feat(video): add Top5Picks composition and Root"
```

---

## Task 7: Preview in Remotion Studio

**Step 1: Launch studio**

```bash
cd video && npm run start
```

Expected: Browser opens at `http://localhost:3000` with Remotion Studio. You'll see `Top5Picks` composition listed.

**Step 2: Check each scene**

In Remotion Studio:
- Scrub to frame 0 → should see Intro (black bg, "TOP 5 PLAYS" text)
- Scrub to frame ~75 → should see Pick #1 card (Cason Wallace)
- Scrub to frame ~165 → should see Pick #2 (Jaylen Brown)
- Scrub to frame ~420 → should see Outro

If you see blank white frames: font or import error. Check the browser console for errors.

**Step 3: Fix any issues found during preview, then commit if clean**

---

## Task 8: Render to MP4

**Step 1: Render**

```bash
cd video && npm run render
```

Expected output (takes 1–3 min):
```
Rendering composition Top5Picks...
✓ Rendered to video/out/top5-picks.mp4
```

**Step 2: Verify output**

```bash
ls -lh video/out/top5-picks.mp4
```

Expected: File exists, size ~5–25 MB.

Open the file in QuickTime / VLC and verify:
- Vertical 9:16 format ✓
- ~15 seconds long ✓
- Smooth slide transitions ✓
- Hit probability bar animates ✓
- Correct picks in correct order ✓

**Step 3: Commit**

```bash
git add video/
git commit -m "feat(video): render top 5 picks TikTok video"
```

---

## Updating Picks in the Future

Edit `video/src/data/picks.ts` — change players, lines, hit probs, and the `DATE_LABEL`. Then run:

```bash
cd video && npm run render
```

That's it.

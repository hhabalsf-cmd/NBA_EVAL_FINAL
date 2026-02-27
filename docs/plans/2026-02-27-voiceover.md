# TikTok Video Voiceover — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add punchy per-scene ElevenLabs TTS voiceover to the existing Remotion Top 5 Picks TikTok video.

**Architecture:** A Python script generates 7 MP3 files (intro, 5 picks, outro) into `video/public/audio/` via the ElevenLabs SDK. Each scene component gains a Remotion `<Audio src={staticFile(...)}>` that plays at frame 0 of the scene. Video is then re-rendered.

**Tech Stack:** ElevenLabs Python SDK (`elevenlabs`), Remotion `<Audio>` + `staticFile`, Python 3

---

## Task 1: Create audio generation script

**Files:**
- Create: `video/generate_audio.py`

**Step 1: Create the public/audio directory**

```bash
mkdir -p video/public/audio
```

**Step 2: Install ElevenLabs SDK if not already present**

```bash
pip show elevenlabs || pip install elevenlabs
```

Expected: either shows package info, or installs it with no errors.

**Step 3: Create `video/generate_audio.py`**

```python
"""
Generate voiceover MP3s for the TikTok Top 5 Picks video.
Outputs 7 files to video/public/audio/.

Usage:
    ELEVENLABS_API_KEY=your_key python video/generate_audio.py
"""

import os
from pathlib import Path
from elevenlabs import ElevenLabs, VoiceSettings

VOICE_ID = "onwK4e9ZLuTAKqWW03F9"  # Daniel — male, authoritative
MODEL_ID = "eleven_multilingual_v2"
OUTPUT_DIR = Path(__file__).parent / "public" / "audio"

SCRIPTS = {
    "intro": "Tonight's top 5 NBA prop picks.",
    "pick-1": "Number one. Cason Wallace, over 14.5 PRA.",
    "pick-2": "Number two. Jaylen Brown, over 6.5 rebounds.",
    "pick-3": "Number three. Jamal Murray, over 3.5 rebounds.",
    "pick-4": "Number four. Derrick White, over 3.5 rebounds.",
    "pick-5": "Number five. Tobias Harris, over 5.5 rebounds.",
    "outro": "Follow for daily picks.",
}


def main():
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise EnvironmentError("ELEVENLABS_API_KEY environment variable not set")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    client = ElevenLabs(api_key=api_key)

    for name, text in SCRIPTS.items():
        out_path = OUTPUT_DIR / f"{name}.mp3"
        print(f"Generating {out_path.name}: \"{text}\"")

        audio = client.text_to_speech.convert(
            text=text,
            voice_id=VOICE_ID,
            model_id=MODEL_ID,
            voice_settings=VoiceSettings(
                stability=0.55,
                similarity_boost=0.80,
                style=0.0,
                speed=1.05,
                use_speaker_boost=True,
            ),
            output_format="mp3_44100_128",
        )

        with open(out_path, "wb") as f:
            for chunk in audio:
                f.write(chunk)

        print(f"  ✓ {out_path} ({out_path.stat().st_size // 1024} KB)")

    print("\nAll audio files generated.")


if __name__ == "__main__":
    main()
```

**Step 4: Run the script**

```bash
python video/generate_audio.py
```

Expected output:
```
Generating intro.mp3: "Tonight's top 5 NBA prop picks."
  ✓ video/public/audio/intro.mp3 (XX KB)
Generating pick-1.mp3: "Number one. Cason Wallace, over 14.5 PRA."
  ✓ video/public/audio/pick-1.mp3 (XX KB)
...
All audio files generated.
```

**Step 5: Verify all 7 files exist**

```bash
ls -lh video/public/audio/
```

Expected: 7 `.mp3` files (intro, pick-1 through pick-5, outro), each 20–80 KB.

**Step 6: Commit**

```bash
git add video/generate_audio.py video/public/audio/
git commit -m "feat(video): add ElevenLabs voiceover generation script and audio files"
```

---

## Task 2: Add audio to Intro scene

**Files:**
- Modify: `video/src/scenes/Intro.tsx`

**Step 1: Add Audio import**

In `video/src/scenes/Intro.tsx`, add `Audio` and `staticFile` to the remotion import line:

```tsx
import {
  AbsoluteFill,
  Audio,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
```

**Step 2: Add `<Audio>` inside the return**

Inside the `<AbsoluteFill>` return, add this as the first child (before the basketball emoji div):

```tsx
<Audio src={staticFile("audio/intro.mp3")} />
```

The full return becomes:

```tsx
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
    <Audio src={staticFile("audio/intro.mp3")} />

    {/* Basketball emoji */}
    <div ...>
```

**Step 3: Commit**

```bash
git add video/src/scenes/Intro.tsx
git commit -m "feat(video): add voiceover to Intro scene"
```

---

## Task 3: Add audio to PickSlide scene

**Files:**
- Modify: `video/src/scenes/PickSlide.tsx`

**Step 1: Add Audio import**

Add `Audio` and `staticFile` to the remotion import:

```tsx
import {
  AbsoluteFill,
  Audio,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
```

**Step 2: Add `<Audio>` as the first child of the return**

```tsx
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
    <Audio src={staticFile(`audio/pick-${pick.rank}.mp3`)} />

    {/* Rank badge */}
    <div ...>
```

**Step 3: Commit**

```bash
git add video/src/scenes/PickSlide.tsx
git commit -m "feat(video): add voiceover to PickSlide scene"
```

---

## Task 4: Add audio to Outro scene

**Files:**
- Modify: `video/src/scenes/Outro.tsx`

**Step 1: Add Audio import**

```tsx
import {
  AbsoluteFill,
  Audio,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
```

**Step 2: Add `<Audio>` as the first child of the return**

```tsx
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
    <Audio src={staticFile("audio/outro.mp3")} />

    <div style={{ transform: `scale(${scale})`, opacity, ...}}>
```

**Step 3: Commit**

```bash
git add video/src/scenes/Outro.tsx
git commit -m "feat(video): add voiceover to Outro scene"
```

---

## Task 5: Re-render the video

**Step 1: Render**

```bash
cd video && npm run render
```

Expected: 450 frames rendered, `video/out/top5-picks.mp4` updated. No errors.

**Step 2: Verify output**

```bash
ls -lh video/out/top5-picks.mp4
```

Expected: file exists, size larger than before (~3–10 MB with audio vs ~1.9 MB without).

Open in QuickTime or VLC and verify:
- Voiceover plays on intro ("Tonight's top 5 NBA prop picks.")
- Each pick slide has its own VO line
- Outro says "Follow for daily picks."
- Audio is in sync with the visual content

**Step 3: Commit**

```bash
git add video/out/top5-picks.mp4
git commit -m "feat(video): re-render with voiceover"
```

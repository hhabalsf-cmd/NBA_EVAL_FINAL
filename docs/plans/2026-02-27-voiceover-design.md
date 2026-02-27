# TikTok Video Voiceover — Design Doc

**Date:** 2026-02-27
**Status:** Approved

## Goal

Add a punchy per-scene voiceover to the existing 15s TikTok Top 5 Picks video (`video/out/top5-picks.mp4`), generated via ElevenLabs TTS and embedded into the Remotion composition.

## Approach

Per-scene audio files (Option A): one MP3 per scene, each placed as an `<Audio>` component inside its corresponding scene. Files live in `video/public/audio/` so Remotion can serve them via `staticFile()`.

## Audio Generation

**Script:** `video/generate_audio.py`
- ElevenLabs Python SDK
- Voice: Daniel (`onwK4e9ZLuTAKqWW03F9`) — male, authoritative
- Model: `eleven_multilingual_v2`
- Output format: `mp3_44100_128`
- API key: `ELEVENLABS_API_KEY` env var

**VO scripts:**

| File | Script |
|------|--------|
| `intro.mp3` | "Tonight's top 5 NBA prop picks." |
| `pick-1.mp3` | "Number one. Cason Wallace, over 14.5 PRA." |
| `pick-2.mp3` | "Number two. Jaylen Brown, over 6.5 rebounds." |
| `pick-3.mp3` | "Number three. Jamal Murray, over 3.5 rebounds." |
| `pick-4.mp3` | "Number four. Derrick White, over 3.5 rebounds." |
| `pick-5.mp3` | "Number five. Tobias Harris, over 5.5 rebounds." |
| `outro.mp3` | "Follow for daily picks." |

## Remotion Integration

Each scene gets an `<Audio src={staticFile("audio/<name>.mp3")} />` added at frame 0:

- `Intro.tsx` → `audio/intro.mp3`
- `PickSlide.tsx` → `audio/pick-{pick.rank}.mp3` (dynamic, driven by `pick.rank` prop)
- `Outro.tsx` → `audio/outro.mp3`

No `startFrom` offset needed — audio starts when the scene starts, which is correct.

## Files Changed

| Action | File |
|--------|------|
| Create | `video/generate_audio.py` |
| Create | `video/public/audio/*.mp3` (7 files, generated) |
| Modify | `video/src/scenes/Intro.tsx` |
| Modify | `video/src/scenes/PickSlide.tsx` |
| Modify | `video/src/scenes/Outro.tsx` |
| Re-render | `video/out/top5-picks.mp4` |

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
    "intro": "Are these hitting tonight? Let's find out.",
    "pick-1": "Number one. Kevin Durant, above 30.5 points plus assists.",
    "pick-2": "Number two. Bilal Coulibaly, above 15.5 P.R.A.",
    "pick-3": "Number three. Kawhi Leonard, above 34.5 points plus rebounds.",
    "pick-4": "Number four. Brandin Podziemski, above 10.5 points plus assists.",
    "outro": "Follow for daily predictions.",
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

#!/usr/bin/env python3
"""One-time migration: upload existing model files to Supabase Storage.

Run on the Railway instance that has the volume with all models:
    python scripts/migrate_models_to_supabase.py
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import model_storage
from nba_evaluator import MODEL_DIR


def main():
    # 1. Create bucket if it doesn't exist
    try:
        supa = model_storage._get_storage_client()
        supa.storage.create_bucket(
            model_storage.BUCKET_NAME,
            options={"public": False, "file_size_limit": 52428800},
        )
        print(f"Created bucket '{model_storage.BUCKET_NAME}'")
    except Exception as exc:
        msg = str(exc).lower()
        if "already exists" in msg or "duplicate" in msg:
            print(f"Bucket '{model_storage.BUCKET_NAME}' already exists")
        else:
            print(f"Bucket creation warning (may already exist): {exc}")

    # 2. Upload all player models
    player_models = sorted(MODEL_DIR.glob("*_model.pkl"))
    print(f"\nFound {len(player_models)} player models to upload")

    success = 0
    for i, path in enumerate(player_models, 1):
        player_name = path.stem.replace("_model", "").replace("_", " ")
        ok = model_storage.upload_player_model(player_name, path)
        if ok:
            success += 1
        status = "OK" if ok else "FAILED"
        print(f"  [{i}/{len(player_models)}] {path.name}: {status}")

    print(f"\nPlayer models: {success}/{len(player_models)} uploaded")

    # 3. Upload game model
    game_path = MODEL_DIR / "games" / "game_predictor.pkl"
    if game_path.exists():
        ok = model_storage.upload_game_model(game_path)
        print(f"Game model: {'OK' if ok else 'FAILED'}")
    else:
        print("Game model not found locally, skipping")

    # 4. Verify by listing
    remote_models = model_storage.list_player_models()
    print(f"\nVerification: {len(remote_models)} player models in Supabase Storage")

    if len(remote_models) < len(player_models):
        print("WARNING: Remote count is less than local count — some uploads may have failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

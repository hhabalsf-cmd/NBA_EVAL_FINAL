"""
One-time bootstrap: populate player_id_map by matching player_game_logs against BDL.

Run this BEFORE deleting player_game_logs data.

Usage:
    python scripts/build_player_id_map.py

Requires .env with DATABASE_URL and BALLDONTLIE_API_KEY set.
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# Make project root importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from bdl_id_mapper import get_player_mapper

def main():
    print("Building player_id_map from player_game_logs + BDL API...")
    mapper = get_player_mapper()
    count = mapper.build_full_mapping()
    print(f"\nDone. {count} player mappings upserted into player_id_map.")
    if count == 0:
        print("Zero mappings — check that player_game_logs has rows with player_name populated.")

if __name__ == "__main__":
    main()

"""Service layer for data fetching operations."""
import sys
from pathlib import Path
from typing import Optional, Dict, List

# Add parent directory to path to import existing modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from nba_evaluator import NBADataScraper, OddsAPI


class DataService:
    """Wraps NBADataScraper for API use."""

    def __init__(self):
        self.scraper = NBADataScraper()
        self.odds_api = OddsAPI()

    def get_todays_games(self) -> List[Dict]:
        """Get today's NBA games."""
        games_df = self.scraper.get_todays_games()
        if games_df.empty:
            return []

        games = []
        for _, row in games_df.iterrows():
            games.append({
                "game_id": row.get('GAME_ID'),
                "home_team_id": row.get('HOME_TEAM_ID'),
                "visitor_team_id": row.get('VISITOR_TEAM_ID'),
                "game_status": row.get('GAME_STATUS_TEXT'),
                "game_date": str(row.get('GAME_DATE_EST', ''))
            })

        return games

    def get_player_game_log(self, player_id: int, seasons: Optional[List[str]] = None) -> List[Dict]:
        """Get player's game log."""
        df = self.scraper.get_player_game_log(player_id, seasons)
        if df is None or df.empty:
            return []

        return df.to_dict('records')

    def get_team_defensive_stats(self) -> Dict:
        """Get team defensive stats."""
        return self.scraper.get_team_defensive_stats()

    def get_injury_report(self) -> Dict:
        """Get injury report."""
        return self.scraper.get_injury_report()

    def get_todays_props(self) -> List[Dict]:
        """Get today's player props from Odds API."""
        return self.odds_api.get_all_todays_props()

    def check_odds_api_usage(self) -> Optional[Dict]:
        """Check Odds API remaining requests."""
        return self.odds_api.check_remaining_requests()

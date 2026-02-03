"""
SQLite database helper for tracking picks history and performance metrics.
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
import time

DB_PATH = Path(__file__).parent / "picks_history.db"


def get_connection():
    """Get database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database schema."""
    conn = get_connection()
    cursor = conn.cursor()

    # Original picks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            player TEXT NOT NULL,
            stat TEXT NOT NULL,
            line REAL NOT NULL,
            prediction REAL NOT NULL,
            direction TEXT NOT NULL,
            edge REAL NOT NULL,
            confidence REAL,
            opponent TEXT,
            is_home INTEGER,
            actual_result REAL,
            won INTEGER
        )
    """)

    # Add new columns if they don't exist (for migration)
    columns_to_add = [
        ("model_type", "TEXT DEFAULT 'unknown'"),
        ("game_date", "TEXT"),
        ("player_id", "INTEGER"),
        ("team_abbrev", "TEXT"),
        ("graded_at", "TEXT"),
    ]

    # Get existing columns
    cursor.execute("PRAGMA table_info(picks)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    for col_name, col_def in columns_to_add:
        if col_name not in existing_columns:
            cursor.execute(f"ALTER TABLE picks ADD COLUMN {col_name} {col_def}")

    conn.commit()
    conn.close()


def save_pick(pick_data: dict) -> int:
    """
    Save a pick to the database.

    Args:
        pick_data: Dict with keys: player, stat, line, prediction, direction,
                   edge, confidence, opponent, is_home, model_type, game_date,
                   player_id, team_abbrev

    Returns:
        The ID of the inserted pick
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO picks (timestamp, player, stat, line, prediction, direction,
                          edge, confidence, opponent, is_home, model_type,
                          game_date, player_id, team_abbrev)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(),
        pick_data.get('player'),
        pick_data.get('stat'),
        pick_data.get('line'),
        pick_data.get('prediction'),
        pick_data.get('direction'),
        pick_data.get('edge'),
        pick_data.get('confidence'),
        pick_data.get('opponent'),
        pick_data.get('is_home', 0),
        pick_data.get('model_type', 'unknown'),
        pick_data.get('game_date'),
        pick_data.get('player_id'),
        pick_data.get('team_abbrev')
    ))

    pick_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return pick_id


def get_picks_history(days: int = 30) -> list:
    """
    Get picks history for the last N days.

    Args:
        days: Number of days to look back (default 30)

    Returns:
        List of pick dicts
    """
    conn = get_connection()
    cursor = conn.cursor()

    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    cursor.execute("""
        SELECT * FROM picks
        WHERE timestamp >= ?
        ORDER BY timestamp DESC
    """, (cutoff,))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_all_picks() -> list:
    """Get all picks in the database."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM picks ORDER BY timestamp DESC")

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def update_pick_result(pick_id: int, actual_result: float, line: float, direction: str):
    """
    Update a pick with the actual result and win/loss status.

    Args:
        pick_id: The pick ID to update
        actual_result: The actual stat value
        line: The betting line
        direction: "OVER" or "UNDER"
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Determine if the pick won
    if direction == "OVER":
        won = 1 if actual_result > line else 0
    else:
        won = 1 if actual_result < line else 0

    # Handle push (exactly hit the line)
    if actual_result == line:
        won = None  # Push

    cursor.execute("""
        UPDATE picks
        SET actual_result = ?, won = ?
        WHERE id = ?
    """, (actual_result, won, pick_id))

    conn.commit()
    conn.close()


def delete_pick(pick_id: int):
    """Delete a pick from the database."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM picks WHERE id = ?", (pick_id,))

    conn.commit()
    conn.close()


def get_performance_stats() -> dict:
    """
    Calculate performance statistics.

    Returns:
        Dict with: total_picks, graded_picks, wins, losses, pushes,
                   win_rate, roi, avg_edge_winners, by_stat, by_edge_range
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get all graded picks (where won is not null)
    cursor.execute("""
        SELECT * FROM picks WHERE won IS NOT NULL
    """)
    graded = [dict(row) for row in cursor.fetchall()]

    # Get total picks
    cursor.execute("SELECT COUNT(*) FROM picks")
    total_picks = cursor.fetchone()[0]

    conn.close()

    if not graded:
        return {
            'total_picks': total_picks,
            'graded_picks': 0,
            'wins': 0,
            'losses': 0,
            'pushes': 0,
            'win_rate': 0.0,
            'roi': 0.0,
            'avg_edge_winners': 0.0,
            'by_stat': {},
            'by_edge_range': {}
        }

    wins = sum(1 for p in graded if p['won'] == 1)
    losses = sum(1 for p in graded if p['won'] == 0)
    pushes = sum(1 for p in graded if p['won'] is None)

    # Win rate (excluding pushes)
    decided = wins + losses
    win_rate = (wins / decided * 100) if decided > 0 else 0.0

    # ROI calculation (assuming -110 odds, risk 1.1 to win 1.0)
    # Each win: +1.0 unit, each loss: -1.1 units
    profit = (wins * 1.0) - (losses * 1.1)
    total_risked = decided * 1.1
    roi = (profit / total_risked * 100) if total_risked > 0 else 0.0

    # Average edge on winners
    winners = [p for p in graded if p['won'] == 1]
    avg_edge_winners = sum(abs(p['edge']) for p in winners) / len(winners) if winners else 0.0

    # Performance by stat
    by_stat = {}
    for stat in ['PTS', 'REB', 'AST', 'PRA']:
        stat_picks = [p for p in graded if p['stat'] == stat and p['won'] is not None]
        if stat_picks:
            stat_wins = sum(1 for p in stat_picks if p['won'] == 1)
            stat_decided = sum(1 for p in stat_picks if p['won'] in [0, 1])
            by_stat[stat] = {
                'total': len(stat_picks),
                'wins': stat_wins,
                'win_rate': (stat_wins / stat_decided * 100) if stat_decided > 0 else 0.0
            }

    # Performance by edge range
    edge_ranges = [(5, 8), (8, 12), (12, 100)]
    by_edge_range = {}
    for low, high in edge_ranges:
        range_picks = [p for p in graded if low <= abs(p['edge']) < high and p['won'] is not None]
        if range_picks:
            range_wins = sum(1 for p in range_picks if p['won'] == 1)
            range_decided = sum(1 for p in range_picks if p['won'] in [0, 1])
            label = f"{low}-{high}%" if high < 100 else f"{low}%+"
            by_edge_range[label] = {
                'total': len(range_picks),
                'wins': range_wins,
                'win_rate': (range_wins / range_decided * 100) if range_decided > 0 else 0.0
            }

    return {
        'total_picks': total_picks,
        'graded_picks': len(graded),
        'wins': wins,
        'losses': losses,
        'pushes': pushes,
        'win_rate': win_rate,
        'roi': roi,
        'avg_edge_winners': avg_edge_winners,
        'by_stat': by_stat,
        'by_edge_range': by_edge_range
    }


def get_cumulative_profit() -> list:
    """
    Get cumulative profit over time for charting.

    Returns:
        List of dicts with: date, profit, cumulative_profit
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT timestamp, won FROM picks
        WHERE won IS NOT NULL
        ORDER BY timestamp ASC
    """)

    rows = cursor.fetchall()
    conn.close()

    results = []
    cumulative = 0.0

    for row in rows:
        if row['won'] == 1:
            profit = 1.0
        elif row['won'] == 0:
            profit = -1.1
        else:
            profit = 0.0

        cumulative += profit
        results.append({
            'date': row['timestamp'][:10],  # Just the date part
            'profit': profit,
            'cumulative_profit': round(cumulative, 2)
        })

    return results


def get_pending_picks() -> List[Dict]:
    """Get all picks that haven't been graded yet."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM picks
        WHERE won IS NULL
        ORDER BY timestamp DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_picks_for_date(game_date: str) -> List[Dict]:
    """Get all picks for a specific game date."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM picks
        WHERE game_date = ?
        ORDER BY timestamp DESC
    """, (game_date,))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def auto_grade_picks(scraper=None) -> Dict:
    """
    Automatically grade pending picks by fetching actual results from NBA API.

    Args:
        scraper: Optional NBADataScraper instance (will create one if not provided)

    Returns:
        Dict with: graded_count, errors, results
    """
    # Import here to avoid circular imports
    if scraper is None:
        from nba_evaluator import NBADataScraper
        scraper = NBADataScraper()

    pending = get_pending_picks()
    if not pending:
        return {'graded_count': 0, 'errors': [], 'results': []}

    graded_count = 0
    errors = []
    results = []

    # Group picks by player to reduce API calls
    players_processed = {}

    for pick in pending:
        player_name = pick['player']
        player_id = pick.get('player_id')
        game_date = pick.get('game_date')
        stat = pick['stat']

        try:
            # Get player ID if not stored
            if not player_id:
                player_info = scraper.get_player_info(player_name)
                if not player_info:
                    errors.append(f"Could not find player: {player_name}")
                    continue
                player_id = player_info['player_id']

            # Get game log (use cached if we already fetched for this player)
            if player_id not in players_processed:
                game_log = scraper.get_player_game_log(player_id, seasons=['2025-26', '2024-25'])
                players_processed[player_id] = game_log
                time.sleep(0.5)  # Rate limiting
            else:
                game_log = players_processed[player_id]

            if game_log is None or game_log.empty:
                errors.append(f"No game log for {player_name}")
                continue

            # Find the game for this pick
            game_log['GAME_DATE'] = game_log['GAME_DATE'].astype(str)

            # Match by game date if available
            if game_date:
                game_match = game_log[game_log['GAME_DATE'].str.contains(game_date[:10])]
            else:
                # Try to match by opponent
                opponent = pick.get('opponent', '')
                if opponent:
                    game_match = game_log[game_log['MATCHUP'].str.contains(opponent)]
                else:
                    continue

            if game_match.empty:
                # Game hasn't happened yet or no match found
                continue

            # Get the actual stat value
            game = game_match.iloc[0]

            if stat == 'PRA':
                actual = game['PTS'] + game['REB'] + game['AST']
            elif stat in game:
                actual = game[stat]
            else:
                errors.append(f"Stat {stat} not found for {player_name}")
                continue

            # Update the pick
            update_pick_result(pick['id'], float(actual), pick['line'], pick['direction'])

            # Mark as graded
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE picks SET graded_at = ? WHERE id = ?",
                          (datetime.now().isoformat(), pick['id']))
            conn.commit()
            conn.close()

            # Determine result
            line = pick['line']
            direction = pick['direction']
            if direction == "OVER":
                won = actual > line
            else:
                won = actual < line

            results.append({
                'player': player_name,
                'stat': stat,
                'line': line,
                'prediction': pick['prediction'],
                'actual': actual,
                'direction': direction,
                'won': won,
                'model_type': pick.get('model_type', 'unknown')
            })

            graded_count += 1

        except Exception as e:
            errors.append(f"Error grading {player_name}: {str(e)}")

    return {
        'graded_count': graded_count,
        'errors': errors,
        'results': results
    }


def get_performance_by_model() -> Dict:
    """
    Get performance statistics broken down by model type.

    Returns:
        Dict with model types as keys, each containing win_rate, total, wins, roi
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT model_type, won, edge FROM picks
        WHERE won IS NOT NULL
    """)

    rows = cursor.fetchall()
    conn.close()

    # Group by model type
    model_stats = {}
    for row in rows:
        model = row['model_type'] or 'unknown'
        if model not in model_stats:
            model_stats[model] = {'wins': 0, 'losses': 0, 'total': 0, 'edges': []}

        model_stats[model]['total'] += 1
        if row['won'] == 1:
            model_stats[model]['wins'] += 1
            model_stats[model]['edges'].append(abs(row['edge']))
        elif row['won'] == 0:
            model_stats[model]['losses'] += 1

    # Calculate win rates and ROI for each model
    results = {}
    for model, stats in model_stats.items():
        decided = stats['wins'] + stats['losses']
        win_rate = (stats['wins'] / decided * 100) if decided > 0 else 0.0

        # ROI calculation (assuming -110 odds)
        profit = (stats['wins'] * 1.0) - (stats['losses'] * 1.1)
        total_risked = decided * 1.1
        roi = (profit / total_risked * 100) if total_risked > 0 else 0.0

        avg_edge = sum(stats['edges']) / len(stats['edges']) if stats['edges'] else 0.0

        results[model] = {
            'total': stats['total'],
            'wins': stats['wins'],
            'losses': stats['losses'],
            'win_rate': round(win_rate, 1),
            'roi': round(roi, 1),
            'avg_edge_winners': round(avg_edge, 1)
        }

    return results


def get_performance_by_model_and_stat() -> Dict:
    """
    Get detailed performance breakdown by model type AND stat type.

    Returns:
        Nested dict: {model_type: {stat: {win_rate, total, wins}}}
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT model_type, stat, won, edge FROM picks
        WHERE won IS NOT NULL
    """)

    rows = cursor.fetchall()
    conn.close()

    # Group by model and stat
    data = {}
    for row in rows:
        model = row['model_type'] or 'unknown'
        stat = row['stat']

        if model not in data:
            data[model] = {}
        if stat not in data[model]:
            data[model][stat] = {'wins': 0, 'losses': 0, 'total': 0}

        data[model][stat]['total'] += 1
        if row['won'] == 1:
            data[model][stat]['wins'] += 1
        elif row['won'] == 0:
            data[model][stat]['losses'] += 1

    # Calculate win rates
    results = {}
    for model, stats in data.items():
        results[model] = {}
        for stat, counts in stats.items():
            decided = counts['wins'] + counts['losses']
            win_rate = (counts['wins'] / decided * 100) if decided > 0 else 0.0
            results[model][stat] = {
                'total': counts['total'],
                'wins': counts['wins'],
                'losses': counts['losses'],
                'win_rate': round(win_rate, 1)
            }

    return results


# Initialize database on import
init_db()

"""
SQLite database helper for tracking picks history and performance metrics.
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
import time

DB_PATH = Path(__file__).parent / "picks_history.db"
EXCEL_PATH = Path(__file__).parent / "nba_picks_tracker.xlsx"


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
        ("voided", "INTEGER DEFAULT 0"),  # 1 = DNP/voided, not counted in performance
        ("void_reason", "TEXT"),  # Reason for void (DNP, postponed, etc.)
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


def void_pick(pick_id: int, reason: str = "DNP"):
    """
    Void a pick (DNP, postponed, etc.) - removes from performance calculations.

    Args:
        pick_id: The pick ID to void
        reason: Reason for voiding (DNP, postponed, injury, etc.)
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE picks
        SET voided = 1, void_reason = ?, won = NULL, actual_result = NULL
        WHERE id = ?
    """, (reason, pick_id))

    conn.commit()
    conn.close()


def get_voided_picks() -> List[Dict]:
    """Get all voided picks."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM picks
        WHERE voided = 1
        ORDER BY timestamp DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def unvoid_pick(pick_id: int):
    """Restore a voided pick back to pending status."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE picks
        SET voided = 0, void_reason = NULL
        WHERE id = ?
    """, (pick_id,))

    conn.commit()
    conn.close()


def reset_pick_to_pending(pick_id: int):
    """Reset a graded pick back to pending status (clears result)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE picks
        SET won = NULL, actual_result = NULL, graded_at = NULL
        WHERE id = ?
    """, (pick_id,))

    conn.commit()
    conn.close()


def reset_all_graded_for_date(game_date: str) -> int:
    """Reset all graded picks for a specific date back to pending.

    Args:
        game_date: Date string (YYYY-MM-DD format)

    Returns:
        Number of picks reset
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Count how many will be affected
    cursor.execute("""
        SELECT COUNT(*) FROM picks
        WHERE game_date LIKE ? AND won IS NOT NULL AND (voided IS NULL OR voided = 0)
    """, (f"{game_date}%",))
    count = cursor.fetchone()[0]

    # Reset them
    cursor.execute("""
        UPDATE picks
        SET won = NULL, actual_result = NULL, graded_at = NULL
        WHERE game_date LIKE ? AND won IS NOT NULL AND (voided IS NULL OR voided = 0)
    """, (f"{game_date}%",))

    conn.commit()
    conn.close()

    return count


def get_performance_stats() -> dict:
    """
    Calculate performance statistics (excludes voided picks).

    Returns:
        Dict with: total_picks, graded_picks, wins, losses, pushes,
                   win_rate, roi, avg_edge_winners, by_stat, by_edge_range
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get all graded picks (where won is not null, excludes voided)
    cursor.execute("""
        SELECT * FROM picks WHERE won IS NOT NULL AND (voided IS NULL OR voided = 0)
    """)
    graded = [dict(row) for row in cursor.fetchall()]

    # Get total non-voided picks
    cursor.execute("SELECT COUNT(*) FROM picks WHERE voided IS NULL OR voided = 0")
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
    """Get all picks that haven't been graded yet (excludes voided picks)."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM picks
        WHERE won IS NULL AND (voided IS NULL OR voided = 0)
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

    # Get today's date for comparison
    today = datetime.now().date()

    for pick in pending:
        player_name = pick['player']
        player_id = pick.get('player_id')
        game_date = pick.get('game_date')
        stat = pick['stat']

        try:
            # Skip picks for future games (game date is after today)
            if game_date:
                try:
                    pick_date = datetime.strptime(game_date[:10], '%Y-%m-%d').date()
                    if pick_date > today:
                        # Game is in the future, skip
                        continue
                except ValueError:
                    pass

            # Get player ID if not stored
            if not player_id:
                player_info = scraper.get_player_info(player_name)
                if not player_info:
                    errors.append(f"Could not find player: {player_name}")
                    continue
                player_id = player_info['player_id']

            # Get game log (use cached if we already fetched for this player)
            # ONLY fetch current season to avoid matching old games for DNP players
            if player_id not in players_processed:
                game_log = scraper.get_player_game_log(player_id, seasons=['2025-26'])
                players_processed[player_id] = game_log
                time.sleep(0.5)  # Rate limiting
            else:
                game_log = players_processed[player_id]

            # Find the game for this pick
            opponent = pick.get('opponent', '')
            game_match = None
            player_dnp = False

            if game_date:
                try:
                    # Convert ISO date to NBA API format (e.g., "2026-02-03" -> "Feb 03, 2026")
                    dt = datetime.strptime(game_date[:10], '%Y-%m-%d')
                    nba_date_format = dt.strftime('%b %d, %Y')

                    # Check if player has any games this season
                    if game_log is None or game_log.empty:
                        # Player has no games at all this season
                        # Check if the game date is in the past - if so, it's a DNP
                        if dt.date() <= today:
                            player_dnp = True
                    else:
                        game_log['GAME_DATE'] = game_log['GAME_DATE'].astype(str)

                        # First try exact date match
                        game_match = game_log[game_log['GAME_DATE'] == nba_date_format]

                        # Filter by opponent if we have one and multiple games
                        if not game_match.empty and opponent and len(game_match) > 1:
                            opponent_match = game_match[game_match['MATCHUP'].str.contains(opponent)]
                            if not opponent_match.empty:
                                game_match = opponent_match

                        # If no exact date match, try +/- 1 day (games sometimes shift dates due to timezone)
                        # But REQUIRE opponent match to avoid grading wrong games
                        if game_match.empty and opponent:
                            dt_minus1 = (dt - timedelta(days=1)).strftime('%b %d, %Y')
                            dt_plus1 = (dt + timedelta(days=1)).strftime('%b %d, %Y')
                            nearby_games = game_log[game_log['GAME_DATE'].isin([dt_minus1, dt_plus1])]

                            # Only use nearby date if opponent also matches
                            if not nearby_games.empty:
                                opponent_match = nearby_games[nearby_games['MATCHUP'].str.contains(opponent)]
                                if not opponent_match.empty:
                                    game_match = opponent_match

                        # If no game found but date is in the past, player likely DNP'd
                        if (game_match is None or game_match.empty) and dt.date() <= today:
                            # Check if team played by looking at other players' games on this date
                            # For now, mark as DNP if game date has passed
                            player_dnp = True

                except ValueError:
                    # Date parsing failed - skip this pick
                    continue

            # Handle DNP - void the pick automatically
            if player_dnp:
                void_pick(pick['id'], "DNP")
                results.append({
                    'player': player_name,
                    'stat': stat,
                    'line': pick['line'],
                    'prediction': pick['prediction'],
                    'actual': None,
                    'direction': pick['direction'],
                    'won': None,
                    'voided': True,
                    'void_reason': 'DNP',
                    'model_type': pick.get('model_type', 'unknown')
                })
                continue

            # NO FALLBACK - if we can't find a date match, the game hasn't happened yet
            # Do NOT match by opponent only as this would grade using old games
            if game_match is None or game_match.empty:
                # Game not found for this date - likely hasn't been played yet
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

    # Count voided picks
    voided_count = sum(1 for r in results if r.get('voided'))

    return {
        'graded_count': graded_count,
        'voided_count': voided_count,
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
        WHERE won IS NOT NULL AND (voided IS NULL OR voided = 0)
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
        WHERE won IS NOT NULL AND (voided IS NULL OR voided = 0)
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


def export_to_excel() -> str:
    """
    Export all picks and performance stats to an Excel file with multiple sheets.

    Returns:
        Path to the created Excel file
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils.dataframe import dataframe_to_rows
        import pandas as pd
    except ImportError:
        print("⚠️ openpyxl not installed. Run: pip install openpyxl")
        return None

    wb = Workbook()

    # Define styles
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    win_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    loss_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    pending_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # ==================== SHEET 1: All Picks ====================
    ws_picks = wb.active
    ws_picks.title = "All Picks"

    all_picks = get_all_picks()

    # Headers
    headers = ["ID", "Date", "Player", "Stat", "Direction", "Line", "Prediction", "Edge %",
               "Opponent", "Home/Away", "Model", "Result", "Actual", "Won"]
    for col, header in enumerate(headers, 1):
        cell = ws_picks.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border

    # Data rows
    for row_idx, pick in enumerate(all_picks, 2):
        data = [
            pick['id'],
            pick['timestamp'][:10] if pick.get('timestamp') else '',
            pick['player'],
            pick['stat'],
            pick['direction'],
            pick['line'],
            round(pick['prediction'], 1),
            round(pick['edge'], 1) if pick.get('edge') else 0,
            pick.get('opponent', ''),
            'HOME' if pick.get('is_home') else 'AWAY',
            (pick.get('model_type') or 'unknown').replace('_', ' ').title(),
            'WIN' if pick.get('won') == 1 else 'LOSS' if pick.get('won') == 0 else 'PENDING',
            round(pick['actual_result'], 1) if pick.get('actual_result') is not None else '',
            pick.get('won', '')
        ]

        for col, value in enumerate(data, 1):
            cell = ws_picks.cell(row=row_idx, column=col, value=value)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='center')

            # Color code by result
            if pick.get('won') == 1:
                cell.fill = win_fill
            elif pick.get('won') == 0:
                cell.fill = loss_fill
            elif pick.get('won') is None:
                cell.fill = pending_fill

    # Auto-adjust column widths
    for col in ws_picks.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        ws_picks.column_dimensions[column].width = min(max_length + 2, 25)

    # ==================== SHEET 2: Pending Picks ====================
    ws_pending = wb.create_sheet("Pending Picks")

    pending = get_pending_picks()
    pending_sorted = sorted(pending, key=lambda x: abs(x.get('edge', 0)), reverse=True)

    headers_pending = ["Player", "Stat", "Direction", "Line", "Prediction", "Edge %",
                       "Opponent", "Game Date", "Model"]
    for col, header in enumerate(headers_pending, 1):
        cell = ws_pending.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border

    for row_idx, pick in enumerate(pending_sorted, 2):
        data = [
            pick['player'],
            pick['stat'],
            pick['direction'],
            pick['line'],
            round(pick['prediction'], 1),
            round(pick['edge'], 1) if pick.get('edge') else 0,
            pick.get('opponent', ''),
            pick.get('game_date', '')[:10] if pick.get('game_date') else '',
            (pick.get('model_type') or 'unknown').replace('_', ' ').title()
        ]

        for col, value in enumerate(data, 1):
            cell = ws_pending.cell(row=row_idx, column=col, value=value)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='center')

            # Highlight high edge picks
            edge = pick.get('edge', 0)
            if abs(edge) >= 30:
                cell.fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
            elif abs(edge) >= 20:
                cell.fill = PatternFill(start_color="FFFFE0", end_color="FFFFE0", fill_type="solid")

    for col in ws_pending.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        ws_pending.column_dimensions[column].width = min(max_length + 2, 25)

    # ==================== SHEET 3: Performance Summary ====================
    ws_perf = wb.create_sheet("Performance")

    stats = get_performance_stats()
    model_stats = get_performance_by_model()

    # Overall stats
    ws_perf.cell(row=1, column=1, value="OVERALL PERFORMANCE").font = Font(bold=True, size=14)
    ws_perf.merge_cells('A1:C1')

    overall_data = [
        ("Total Picks", stats['total_picks']),
        ("Graded Picks", stats['graded_picks']),
        ("Wins", stats['wins']),
        ("Losses", stats['losses']),
        ("Win Rate", f"{stats['win_rate']:.1f}%"),
        ("ROI", f"{stats['roi']:+.1f}%"),
        ("Avg Edge (Winners)", f"{stats['avg_edge_winners']:.1f}%"),
        ("Last Updated", datetime.now().strftime("%Y-%m-%d %H:%M"))
    ]

    for row_idx, (label, value) in enumerate(overall_data, 3):
        ws_perf.cell(row=row_idx, column=1, value=label).font = Font(bold=True)
        ws_perf.cell(row=row_idx, column=2, value=value)

    # By Model
    ws_perf.cell(row=13, column=1, value="PERFORMANCE BY MODEL").font = Font(bold=True, size=14)
    ws_perf.merge_cells('A13:E13')

    model_headers = ["Model", "Wins", "Losses", "Win Rate", "ROI"]
    for col, header in enumerate(model_headers, 1):
        cell = ws_perf.cell(row=15, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border

    row_idx = 16
    for model, data in sorted(model_stats.items(), key=lambda x: x[1]['win_rate'], reverse=True):
        model_name = model.replace('_', ' ').title()
        row_data = [model_name, data['wins'], data['losses'], f"{data['win_rate']:.1f}%", f"{data['roi']:+.1f}%"]
        for col, value in enumerate(row_data, 1):
            cell = ws_perf.cell(row=row_idx, column=col, value=value)
            cell.border = thin_border
        row_idx += 1

    # By Stat
    ws_perf.cell(row=row_idx + 2, column=1, value="PERFORMANCE BY STAT").font = Font(bold=True, size=14)
    stat_row = row_idx + 4

    stat_headers = ["Stat", "Wins", "Total", "Win Rate"]
    for col, header in enumerate(stat_headers, 1):
        cell = ws_perf.cell(row=stat_row, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border

    stat_row += 1
    for stat, data in stats.get('by_stat', {}).items():
        row_data = [stat, data['wins'], data['total'], f"{data['win_rate']:.1f}%"]
        for col, value in enumerate(row_data, 1):
            cell = ws_perf.cell(row=stat_row, column=col, value=value)
            cell.border = thin_border
        stat_row += 1

    # By Edge Range
    ws_perf.cell(row=stat_row + 2, column=1, value="PERFORMANCE BY EDGE RANGE").font = Font(bold=True, size=14)
    edge_row = stat_row + 4

    edge_headers = ["Edge Range", "Wins", "Total", "Win Rate"]
    for col, header in enumerate(edge_headers, 1):
        cell = ws_perf.cell(row=edge_row, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border

    edge_row += 1
    for edge_range, data in stats.get('by_edge_range', {}).items():
        row_data = [edge_range, data['wins'], data['total'], f"{data['win_rate']:.1f}%"]
        for col, value in enumerate(row_data, 1):
            cell = ws_perf.cell(row=edge_row, column=col, value=value)
            cell.border = thin_border
        edge_row += 1

    ws_perf.column_dimensions['A'].width = 20
    ws_perf.column_dimensions['B'].width = 12
    ws_perf.column_dimensions['C'].width = 12
    ws_perf.column_dimensions['D'].width = 12
    ws_perf.column_dimensions['E'].width = 12

    # ==================== SHEET 4: Profit Tracker ====================
    ws_profit = wb.create_sheet("Profit Tracker")

    profit_data = get_cumulative_profit()

    headers_profit = ["Date", "Profit/Loss", "Cumulative Profit"]
    for col, header in enumerate(headers_profit, 1):
        cell = ws_profit.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border

    for row_idx, entry in enumerate(profit_data, 2):
        data = [entry['date'], entry['profit'], entry['cumulative_profit']]
        for col, value in enumerate(data, 1):
            cell = ws_profit.cell(row=row_idx, column=col, value=value)
            cell.border = thin_border
            if col == 2:  # Profit column
                if value > 0:
                    cell.fill = win_fill
                elif value < 0:
                    cell.fill = loss_fill

    for col in ws_profit.columns:
        ws_profit.column_dimensions[col[0].column_letter].width = 18

    # Save the workbook
    wb.save(EXCEL_PATH)

    return str(EXCEL_PATH)


# Initialize database on import
init_db()

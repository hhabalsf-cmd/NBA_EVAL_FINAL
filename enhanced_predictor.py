"""
Enhanced NBA Player Props Predictor

Advanced ML system with:
- XGBoost and LightGBM models
- Stacking ensemble with meta-learner
- Bayesian hyperparameter optimization
- Advanced feature engineering
- Calibrated probability outputs
- Quantile regression for uncertainty
"""
import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor, StackingRegressor
from sklearn.linear_model import Ridge, BayesianRidge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.isotonic import IsotonicRegression
from sklearn.base import clone as sklearn_clone
from scipy import stats
from pathlib import Path
import joblib
import warnings
warnings.filterwarnings('ignore')

# Optional imports - handle both ImportError and runtime errors
XGB_AVAILABLE = False
LGB_AVAILABLE = False
xgb = None
lgb = None

try:
    import xgboost as xgb
    # Test that it actually works
    _ = xgb.XGBRegressor()
    XGB_AVAILABLE = True
except Exception:
    XGB_AVAILABLE = False

try:
    import lightgbm as lgb
    # Test that it actually works
    _ = lgb.LGBMRegressor()
    LGB_AVAILABLE = True
except Exception:
    LGB_AVAILABLE = False

try:
    from sklearn.ensemble import HistGradientBoostingRegressor
    HIST_GB_AVAILABLE = True
except ImportError:
    HIST_GB_AVAILABLE = False


class EnhancedFeatureEngineer:
    """
    Advanced feature engineering with:
    - Opponent-specific adjustments
    - Matchup-based features
    - Situational context
    - Interaction terms
    """

    # Fallback defensive tier lists when live team_stats are unavailable
    _FALLBACK_ELITE_DEFENSES = ['BOS', 'CLE', 'OKC', 'MIN', 'MEM']
    _FALLBACK_WEAK_DEFENSES = ['WAS', 'UTA', 'POR', 'SAS', 'DET']

    @staticmethod
    def _compute_defense_tiers(team_stats: dict) -> tuple[set, set, dict]:
        """
        Compute elite/weak defense sets and per-team rank from live team_stats.

        Returns:
            (elite_teams, weak_teams, rank_map) where rank_map[abbrev] = 1..30
            (rank 1 = best defense / lowest def_rating).
        """
        if not team_stats:
            return (
                set(EnhancedFeatureEngineer._FALLBACK_ELITE_DEFENSES),
                set(EnhancedFeatureEngineer._FALLBACK_WEAK_DEFENSES),
                {},
            )

        # Sort ascending by def_rating (lower = better defense)
        sorted_teams = sorted(
            [(abbrev, stats.get('def_rating', 112)) for abbrev, stats in team_stats.items()],
            key=lambda x: x[1],
        )
        rank_map = {abbrev: rank + 1 for rank, (abbrev, _) in enumerate(sorted_teams)}
        n = len(sorted_teams)
        top_n = max(1, round(n * 0.17))  # ~top 5 of 30
        bot_n = max(1, round(n * 0.17))
        elite = {abbrev for abbrev, _ in sorted_teams[:top_n]}
        weak = {abbrev for abbrev, _ in sorted_teams[-bot_n:]}
        return elite, weak, rank_map

    @staticmethod
    def create_advanced_features(df, player_info=None, game_info=None,
                                  injuries=None, team_stats=None, vs_stats=None):
        """
        Create comprehensive feature set with advanced engineering.
        """
        df = df.copy()

        # ===== BASIC STAT PROCESSING =====
        if 'MIN' in df.columns and df['MIN'].dtype == 'object':
            df['MIN_NUMERIC'] = df['MIN'].apply(EnhancedFeatureEngineer._parse_minutes)
        elif 'MIN' in df.columns:
            df['MIN_NUMERIC'] = df['MIN']

        # Ensure numeric types
        for col in ['PTS', 'REB', 'AST', 'FGA', 'FGM', 'FTA', 'FTM', 'FG3M', 'FG3A', 'TOV', 'STL', 'BLK']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # ===== ADVANCED EFFICIENCY METRICS =====
        if all(c in df.columns for c in ['PTS', 'FGA', 'FTA']):
            # True Shooting %
            df['TS_PCT'] = df['PTS'] / (2 * (df['FGA'] + 0.44 * df['FTA']))
            df['TS_PCT'] = df['TS_PCT'].replace([np.inf, -np.inf], np.nan).fillna(0)

            # Points per shot attempt (includes FT)
            df['PTS_PER_SHOT'] = df['PTS'] / (df['FGA'] + 0.44 * df['FTA'])
            df['PTS_PER_SHOT'] = df['PTS_PER_SHOT'].replace([np.inf, -np.inf], np.nan).fillna(0)

        if all(c in df.columns for c in ['FGM', 'FG3M', 'FGA']):
            # Effective FG%
            df['EFG_PCT'] = (df['FGM'] + 0.5 * df['FG3M']) / df['FGA']
            df['EFG_PCT'] = df['EFG_PCT'].replace([np.inf, -np.inf], np.nan).fillna(0)

        # Assist-to-Turnover
        if all(c in df.columns for c in ['AST', 'TOV']):
            df['AST_TOV_RATIO'] = df['AST'] / (df['TOV'] + 0.1)

        # Stocks (Steals + Blocks)
        if all(c in df.columns for c in ['STL', 'BLK']):
            df['STOCKS'] = df['STL'] + df['BLK']

        # Fantasy Points (DraftKings scoring)
        if all(c in df.columns for c in ['PTS', 'REB', 'AST', 'STL', 'BLK', 'TOV']):
            df['FANTASY_PTS'] = (df['PTS'] + 1.25 * df['REB'] + 1.5 * df['AST'] +
                                2.0 * df['STL'] + 2.0 * df['BLK'] - 0.5 * df['TOV'])

        # PRA (Points + Rebounds + Assists)
        if all(c in df.columns for c in ['PTS', 'REB', 'AST']):
            df['PRA'] = df['PTS'] + df['REB'] + df['AST']

        # ===== MULTI-WINDOW ROLLING FEATURES =====
        windows = [3, 5, 7, 10, 15, 20]
        core_stats = ['PTS', 'REB', 'AST', 'MIN_NUMERIC']
        secondary_stats = ['TS_PCT', 'EFG_PCT', 'FANTASY_PTS', 'PRA', 'FGA', 'STOCKS']

        for stat in core_stats:
            if stat in df.columns:
                for w in windows:
                    df[f'ROLL_{w}_{stat}'] = df[stat].shift(1).rolling(w, min_periods=max(1, w//2)).mean()
                    if w in [5, 10]:
                        df[f'STD_{w}_{stat}'] = df[stat].shift(1).rolling(w, min_periods=3).std()

                # Exponential moving averages (more responsive)
                for span in [3, 5, 10]:
                    df[f'EMA_{span}_{stat}'] = df[stat].shift(1).ewm(span=span, min_periods=2).mean()

        for stat in secondary_stats:
            if stat in df.columns:
                for w in [5, 10]:
                    df[f'ROLL_{w}_{stat}'] = df[stat].shift(1).rolling(w, min_periods=3).mean()

        # ===== TREND FEATURES (Momentum Detection) =====
        for stat in ['PTS', 'REB', 'AST', 'MIN_NUMERIC']:
            if stat in df.columns:
                # Short vs long term comparison
                if f'ROLL_5_{stat}' in df.columns and f'ROLL_20_{stat}' in df.columns:
                    df[f'{stat}_TREND'] = df[f'ROLL_5_{stat}'] - df[f'ROLL_20_{stat}']

                # Very recent trend (3-game vs 7-game)
                if f'ROLL_3_{stat}' in df.columns and f'ROLL_7_{stat}' in df.columns:
                    df[f'{stat}_RECENT_TREND'] = df[f'ROLL_3_{stat}'] - df[f'ROLL_7_{stat}']

                # Acceleration (is trend accelerating?)
                if f'{stat}_TREND' in df.columns:
                    df[f'{stat}_ACCEL'] = df[f'{stat}_TREND'].diff(3)

        # ===== VOLATILITY FEATURES =====
        for stat in ['PTS', 'REB', 'AST']:
            if stat in df.columns:
                # Coefficient of variation (normalized volatility)
                if f'ROLL_10_{stat}' in df.columns and f'STD_10_{stat}' in df.columns:
                    df[f'{stat}_CV'] = df[f'STD_10_{stat}'] / (df[f'ROLL_10_{stat}'] + 0.1)
                    df[f'{stat}_CV'] = df[f'{stat}_CV'].clip(0, 2)

                # Range (max - min) over last 5 games
                df[f'{stat}_RANGE_5'] = (df[stat].shift(1).rolling(5).max() -
                                         df[stat].shift(1).rolling(5).min())

        # ===== REST & SCHEDULE CONTEXT =====
        if 'GAME_DATE' in df.columns:
            df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
            df['DAYS_REST'] = df['GAME_DATE'].diff().dt.days.clip(0, 7).fillna(2)
            df['B2B'] = (df['DAYS_REST'] == 1).astype(int)
            df['EXTENDED_REST'] = (df['DAYS_REST'] >= 3).astype(int)

            # Day of week effects
            df['DAY_OF_WEEK'] = df['GAME_DATE'].dt.dayofweek
            df['IS_WEEKEND'] = df['DAY_OF_WEEK'].isin([5, 6]).astype(int)

        # ===== GAME NUMBER & SEASON PHASE =====
        df['GAME_NUM'] = range(1, len(df) + 1)
        df['SEASON_PHASE'] = pd.cut(df['GAME_NUM'],
                                     bins=[0, 20, 45, 65, 82, 200],
                                     labels=[1, 2, 3, 4, 5]).astype(float)
        # 1=Early, 2=Pre-ASB, 3=Post-ASB, 4=Late, 5=Playoffs

        # ===== WIN/LOSS MOMENTUM =====
        if 'WL' in df.columns:
            df['WL_NUM'] = (df['WL'] == 'W').astype(int)
            df['WIN_STREAK'] = df['WL_NUM'].shift(1).rolling(5, min_periods=1).sum()
            df['LOSS_STREAK'] = (1 - df['WL_NUM']).shift(1).rolling(5, min_periods=1).sum()
            df['RECENT_WIN_PCT'] = df['WL_NUM'].shift(1).rolling(10, min_periods=3).mean()

        # ===== ROLE STABILITY =====
        if 'MIN_NUMERIC' in df.columns:
            df['MIN_CONSISTENCY'] = df['MIN_NUMERIC'].shift(1).rolling(10, min_periods=5).std().fillna(5)
            df['MIN_TREND_RATIO'] = df[f'ROLL_5_MIN_NUMERIC'] / (df[f'ROLL_20_MIN_NUMERIC'] + 1)

        if 'FGA' in df.columns:
            df['USAGE_PROXY'] = df['FGA'].shift(1).rolling(10, min_periods=3).mean()
            df['SHOT_VOLUME_TREND'] = df[f'ROLL_5_FGA'] - df['USAGE_PROXY'] if f'ROLL_5_FGA' in df.columns else 0

        # ===== HOT/COLD STREAKS =====
        for stat in ['PTS', 'PRA']:
            if stat in df.columns and f'STD_10_{stat}' in df.columns:
                df[f'{stat}_ZSCORE'] = ((df[f'ROLL_3_{stat}'] - df[f'ROLL_20_{stat}']) /
                                        (df[f'STD_10_{stat}'] + 0.1))
                df[f'{stat}_ZSCORE'] = df[f'{stat}_ZSCORE'].clip(-3, 3)

        if 'PTS_ZSCORE' in df.columns:
            df['IS_HOT'] = (df['PTS_ZSCORE'] > 1.0).astype(int)
            df['IS_COLD'] = (df['PTS_ZSCORE'] < -1.0).astype(int)

            # Momentum reversion: extreme streaks tend to revert toward mean
            # Positive values = expected upward reversion (cold streak), negative = downward (hot streak)
            df['REVERSION_FACTOR'] = np.where(
                df['PTS_ZSCORE'] > 2.0,
                -(df['PTS_ZSCORE'] - 2.0) * 0.15,   # hot extreme → slight downward pull
                np.where(
                    df['PTS_ZSCORE'] < -2.0,
                    -(df['PTS_ZSCORE'] + 2.0) * 0.15,  # cold extreme → slight upward pull
                    0.0
                )
            )

        # ===== OPPONENT CONTEXT =====
        if team_stats:
            opponent = game_info.get('opponent', '') if game_info else ''
            opp_stats = team_stats.get(opponent, {})

            opp_def_rating = opp_stats.get('def_rating', 112)
            opp_pace = opp_stats.get('pace', 100)

            # Normalized opponent strength (-2 to +2 scale)
            df['OPP_DEF_RATING_NORM'] = (opp_def_rating - 112) / 4
            df['OPP_PACE_NORM'] = (opp_pace - 100) / 4

            # Dynamic defensive tiers (computed from live rankings)
            elite_teams, weak_teams, rank_map = EnhancedFeatureEngineer._compute_defense_tiers(team_stats)
            df['OPP_ELITE_DEF'] = 1 if opponent in elite_teams else 0
            df['OPP_WEAK_DEF'] = 1 if opponent in weak_teams else 0
            df['OPP_DEF_RATING_RANK'] = rank_map.get(opponent, 15)  # 1=best, 30=worst

            # Pace-adjusted projections
            pace_factor = opp_pace / 100
            for stat in ['PTS', 'REB', 'AST']:
                if f'ROLL_5_{stat}' in df.columns:
                    df[f'{stat}_PACE_ADJ'] = df[f'ROLL_5_{stat}'] * pace_factor

        # ===== HOME/AWAY =====
        if game_info:
            df['IS_HOME'] = game_info.get('is_home', 0)
        elif 'MATCHUP' in df.columns:
            df['IS_HOME'] = df['MATCHUP'].str.contains('vs.').astype(int)

        # ===== INJURY CONTEXT =====
        if injuries and player_info:
            team_abbrev = player_info.get('team_abbreviation', '')
            opponent = game_info.get('opponent', '') if game_info else ''

            team_injuries = injuries.get(team_abbrev, {})
            opp_injuries = injuries.get(opponent, {})

            team_out = team_injuries.get('out', 0)
            opp_out = opp_injuries.get('out', 0)
            df['TEAM_INJURIES_OUT'] = team_out
            df['OPP_INJURIES_OUT'] = opp_out

            # Severity-weighted injury boost: star player out counts more
            # Use injury notes if available to differentiate severity
            team_injury_notes = team_injuries.get('notes', [])
            severity_weight = 0.0
            for note in team_injury_notes:
                note_lower = str(note).lower()
                if any(kw in note_lower for kw in ['out for season', 'surgery', 'torn', 'fracture']):
                    severity_weight += 1.0   # long-term out, full usage shift
                elif any(kw in note_lower for kw in ['questionable', 'doubtful', 'game-time']):
                    severity_weight += 0.5   # uncertain, partial usage shift
                else:
                    severity_weight += 0.75  # standard out

            # Fall back to count-based estimate if no notes available
            if not team_injury_notes:
                severity_weight = team_out * 0.75

            df['INJURY_USAGE_BOOST'] = np.minimum(severity_weight, 2.5)

        # ===== VS OPPONENT HISTORY =====
        if vs_stats:
            df['VS_OPP_AVG_PTS'] = vs_stats.get('avg_pts', df['ROLL_10_PTS'].iloc[-1] if 'ROLL_10_PTS' in df.columns else 20)
            df['VS_OPP_AVG_REB'] = vs_stats.get('avg_reb', df['ROLL_10_REB'].iloc[-1] if 'ROLL_10_REB' in df.columns else 5)
            df['VS_OPP_AVG_AST'] = vs_stats.get('avg_ast', df['ROLL_10_AST'].iloc[-1] if 'ROLL_10_AST' in df.columns else 4)
            df['VS_OPP_GAMES'] = vs_stats.get('games', 0)

        # ===== TARGET-ENCODED OPPONENT EFFECTS (Improvement #7) =====
        if 'MATCHUP' in df.columns:
            # Extract opponent abbreviation from matchup string
            df['_OPP_TEAM'] = df['MATCHUP'].apply(
                lambda x: str(x).split()[-1] if pd.notna(x) else ''
            )
            smoothing = 5  # Minimum games for full weight
            for stat_col in ['PTS', 'REB', 'AST']:
                if stat_col in df.columns:
                    global_mean = df[stat_col].shift(1).expanding(min_periods=5).mean()
                    # Group by opponent for leave-one-out encoding
                    opp_stats = df.groupby('_OPP_TEAM')[stat_col].transform(
                        lambda x: x.shift(1).expanding(min_periods=1).mean()
                    )
                    n_vs = df.groupby('_OPP_TEAM')[stat_col].transform(
                        lambda x: x.shift(1).expanding().count()
                    )
                    # Smoothed encoding: blend opponent mean with global mean
                    df[f'OPP_ENC_{stat_col}'] = (
                        (n_vs * opp_stats + smoothing * global_mean) /
                        (n_vs + smoothing)
                    ).fillna(global_mean)
            df.drop(columns=['_OPP_TEAM'], errors='ignore', inplace=True)

        # ===== POSITION FEATURE =====
        if player_info:
            # Map position string to ordinal (PG=0, SG=1, SF=2, PF=3, C=4)
            _pos_map = {'PG': 0, 'SG': 1, 'SF': 2, 'PF': 3, 'C': 4, 'G': 0.5, 'F': 2.5, 'G-F': 1.5, 'F-G': 1.5, 'F-C': 3.5, 'C-F': 3.5}
            raw_pos = str(player_info.get('position', '')).upper().strip()
            df['POSITION_ORD'] = _pos_map.get(raw_pos, 2.0)  # default SF if unknown

            # Position x defensive interactions (centers more impacted by shot-blocking defenses)
            if 'OPP_DEF_RATING_NORM' in df.columns:
                df['POSITION_x_OPP_DEF'] = df['POSITION_ORD'] * df['OPP_DEF_RATING_NORM']
            if 'OPP_PACE_NORM' in df.columns:
                df['POSITION_x_OPP_PACE'] = df['POSITION_ORD'] * df['OPP_PACE_NORM']

        # ===== INTERACTION FEATURES =====
        # B2B + Elite defense = harder game
        if 'B2B' in df.columns and 'OPP_ELITE_DEF' in df.columns:
            df['B2B_VS_ELITE'] = df['B2B'] * df['OPP_ELITE_DEF']

        # Hot streak + Weak defense = potential explosion
        if 'IS_HOT' in df.columns and 'OPP_WEAK_DEF' in df.columns:
            df['HOT_VS_WEAK'] = df['IS_HOT'] * df['OPP_WEAK_DEF']

        # Extended rest + Home = optimal conditions
        if 'EXTENDED_REST' in df.columns and 'IS_HOME' in df.columns:
            df['RESTED_HOME'] = df['EXTENDED_REST'] * df['IS_HOME']

        # High usage + team injuries = usage boost
        if 'USAGE_PROXY' in df.columns and 'TEAM_INJURIES_OUT' in df.columns:
            usage_zscore = (df['USAGE_PROXY'] - df['USAGE_PROXY'].mean()) / (df['USAGE_PROXY'].std() + 0.1)
            df['HIGH_USAGE_INJURIES'] = (usage_zscore > 0.5).astype(int) * df['TEAM_INJURIES_OUT']

        return df

    @staticmethod
    def _parse_minutes(min_str):
        """Parse MM:SS format to decimal minutes."""
        if pd.isna(min_str):
            return 0
        if isinstance(min_str, (int, float)):
            return float(min_str)
        try:
            if ':' in str(min_str):
                parts = str(min_str).split(':')
                return int(parts[0]) + int(parts[1]) / 60
            return float(min_str)
        except:
            return 0

    @staticmethod
    def get_prediction_features(df, is_home=0, opponent='', injuries_team=0,
                                 injuries_opp=0, opp_def_rating=112, opp_pace=100,
                                 days_rest=2, vs_stats=None, all_team_stats=None,
                                 player_info=None, injuries_notes=None):
        """
        Extract features for making a prediction.
        Returns DataFrame with single row of features.
        """
        last = df.iloc[-1]

        features = {
            # Core rolling stats (multiple windows)
            'ROLL_3_PTS': last.get('ROLL_3_PTS', last.get('ROLL_5_PTS', 20)),
            'ROLL_5_PTS': last.get('ROLL_5_PTS', 20),
            'ROLL_7_PTS': last.get('ROLL_7_PTS', last.get('ROLL_5_PTS', 20)),
            'ROLL_10_PTS': last.get('ROLL_10_PTS', 20),
            'ROLL_15_PTS': last.get('ROLL_15_PTS', 20),

            'ROLL_3_REB': last.get('ROLL_3_REB', last.get('ROLL_5_REB', 5)),
            'ROLL_5_REB': last.get('ROLL_5_REB', 5),
            'ROLL_10_REB': last.get('ROLL_10_REB', 5),

            'ROLL_3_AST': last.get('ROLL_3_AST', last.get('ROLL_5_AST', 4)),
            'ROLL_5_AST': last.get('ROLL_5_AST', 4),
            'ROLL_10_AST': last.get('ROLL_10_AST', 4),

            'ROLL_5_MIN_NUMERIC': last.get('ROLL_5_MIN_NUMERIC', 28),
            'ROLL_10_MIN_NUMERIC': last.get('ROLL_10_MIN_NUMERIC', 28),

            # EMA features
            'EMA_3_PTS': last.get('EMA_3_PTS', last.get('EMA_5_PTS', 20)),
            'EMA_5_PTS': last.get('EMA_5_PTS', 20),
            'EMA_10_PTS': last.get('EMA_10_PTS', 20),
            'EMA_5_REB': last.get('EMA_5_REB', 5),
            'EMA_5_AST': last.get('EMA_5_AST', 4),
            'EMA_5_MIN_NUMERIC': last.get('EMA_5_MIN_NUMERIC', 28),

            # Volatility
            'STD_5_PTS': last.get('STD_5_PTS', 5),
            'STD_10_PTS': last.get('STD_10_PTS', 5),
            'STD_5_REB': last.get('STD_5_REB', 2),
            'STD_5_AST': last.get('STD_5_AST', 2),
            'PTS_CV': last.get('PTS_CV', 0.25),
            'PTS_RANGE_5': last.get('PTS_RANGE_5', 10),

            # Trends
            'PTS_TREND': last.get('PTS_TREND', 0),
            'REB_TREND': last.get('REB_TREND', 0),
            'AST_TREND': last.get('AST_TREND', 0),
            'PTS_RECENT_TREND': last.get('PTS_RECENT_TREND', 0),
            'PTS_ACCEL': last.get('PTS_ACCEL', 0),

            # Schedule context
            'DAYS_REST': min(days_rest, 7),
            'B2B': 1 if days_rest == 1 else 0,
            'EXTENDED_REST': 1 if days_rest >= 3 else 0,
            'IS_HOME': is_home,

            # Team momentum
            'WIN_STREAK': last.get('WIN_STREAK', 2.5),
            'LOSS_STREAK': last.get('LOSS_STREAK', 2.5),
            'RECENT_WIN_PCT': last.get('RECENT_WIN_PCT', 0.5),

            # Role stability
            'MIN_CONSISTENCY': last.get('MIN_CONSISTENCY', 5),
            'USAGE_PROXY': last.get('USAGE_PROXY', 15),
            'SHOT_VOLUME_TREND': last.get('SHOT_VOLUME_TREND', 0),

            # Hot/cold
            'PTS_ZSCORE': last.get('PTS_ZSCORE', 0),
            'IS_HOT': last.get('IS_HOT', 0),
            'IS_COLD': last.get('IS_COLD', 0),

            # Season context
            'SEASON_PHASE': last.get('SEASON_PHASE', 2),
            'GAME_NUM': min(last.get('GAME_NUM', 41), 100),

            # Opponent — use dynamic tiers when all_team_stats is available
            'OPP_DEF_RATING_NORM': (opp_def_rating - 112) / 4,
            'OPP_PACE_NORM': (opp_pace - 100) / 4,
        }

        elite_teams, weak_teams, rank_map = EnhancedFeatureEngineer._compute_defense_tiers(all_team_stats or {})
        features.update({
            'OPP_ELITE_DEF': 1 if opponent in elite_teams else 0,
            'OPP_WEAK_DEF': 1 if opponent in weak_teams else 0,
            'OPP_DEF_RATING_RANK': rank_map.get(opponent, 15),  # 1=best defense, 30=worst

            # Pace-adjusted
            'PTS_PACE_ADJ': last.get('PTS_PACE_ADJ', last.get('ROLL_5_PTS', 20) * opp_pace / 100),
            'REB_PACE_ADJ': last.get('REB_PACE_ADJ', last.get('ROLL_5_REB', 5) * opp_pace / 100),
            'AST_PACE_ADJ': last.get('AST_PACE_ADJ', last.get('ROLL_5_AST', 4) * opp_pace / 100),

            # Efficiency
            'ROLL_5_TS_PCT': last.get('ROLL_5_TS_PCT', 0.55),
            'ROLL_5_EFG_PCT': last.get('ROLL_5_EFG_PCT', 0.50),
            'ROLL_5_FANTASY_PTS': last.get('ROLL_5_FANTASY_PTS', 35),
            'ROLL_5_PRA': last.get('ROLL_5_PRA', 30),
            'ROLL_10_PRA': last.get('ROLL_10_PRA', 30),

            # Injuries (severity-weighted)
            'TEAM_INJURIES_OUT': injuries_team,
            'OPP_INJURIES_OUT': injuries_opp,
            'INJURY_USAGE_BOOST': min(
                sum(
                    1.0 if any(kw in str(n).lower() for kw in ['out for season', 'surgery', 'torn', 'fracture'])
                    else 0.5 if any(kw in str(n).lower() for kw in ['questionable', 'doubtful', 'game-time'])
                    else 0.75
                    for n in (injuries_notes or [])
                ) if injuries_notes else injuries_team * 0.75,
                2.5,
            ),

            # Momentum reversion
            'REVERSION_FACTOR': (
                -(last.get('PTS_ZSCORE', 0) - 2.0) * 0.15 if last.get('PTS_ZSCORE', 0) > 2.0
                else -(last.get('PTS_ZSCORE', 0) + 2.0) * 0.15 if last.get('PTS_ZSCORE', 0) < -2.0
                else 0.0
            ),

            # Interactions
            'B2B_VS_ELITE': (1 if days_rest == 1 else 0) * (1 if opponent in elite_teams else 0),
            'HOT_VS_WEAK': last.get('IS_HOT', 0) * (1 if opponent in weak_teams else 0),
            'RESTED_HOME': (1 if days_rest >= 3 else 0) * is_home,

            # Position
            'POSITION_ORD': {
                'PG': 0, 'SG': 1, 'SF': 2, 'PF': 3, 'C': 4,
                'G': 0.5, 'F': 2.5, 'G-F': 1.5, 'F-G': 1.5, 'F-C': 3.5, 'C-F': 3.5,
            }.get(str((player_info or {}).get('position', '')).upper().strip(), 2.0),
        })

        # Position interaction features (computed after update)
        features['POSITION_x_OPP_DEF'] = features['POSITION_ORD'] * features['OPP_DEF_RATING_NORM']
        features['POSITION_x_OPP_PACE'] = features['POSITION_ORD'] * features['OPP_PACE_NORM']

        # VS opponent history
        if vs_stats:
            features['VS_OPP_AVG_PTS'] = vs_stats.get('avg_pts', features['ROLL_10_PTS'])
            features['VS_OPP_AVG_REB'] = vs_stats.get('avg_reb', features['ROLL_10_REB'])
            features['VS_OPP_AVG_AST'] = vs_stats.get('avg_ast', features['ROLL_10_AST'])
            features['VS_OPP_GAMES'] = vs_stats.get('games', 0)
        else:
            features['VS_OPP_AVG_PTS'] = features['ROLL_10_PTS']
            features['VS_OPP_AVG_REB'] = features['ROLL_10_REB']
            features['VS_OPP_AVG_AST'] = features['ROLL_10_AST']
            features['VS_OPP_GAMES'] = 0

        return pd.DataFrame([features])


class EnhancedMLPredictor:
    """
    Advanced ML predictor with:
    - Multiple model types (RF, XGBoost, LightGBM, HistGB)
    - Stacking ensemble with meta-learner
    - Bayesian hyperparameter considerations
    - Quantile regression for uncertainty
    - Calibrated probabilities
    """

    FEATURE_NAMES = [
        # Core rolling (multi-window)
        'ROLL_3_PTS', 'ROLL_5_PTS', 'ROLL_7_PTS', 'ROLL_10_PTS', 'ROLL_15_PTS',
        'ROLL_3_REB', 'ROLL_5_REB', 'ROLL_10_REB',
        'ROLL_3_AST', 'ROLL_5_AST', 'ROLL_10_AST',
        'ROLL_5_MIN_NUMERIC', 'ROLL_10_MIN_NUMERIC',

        # EMA
        'EMA_3_PTS', 'EMA_5_PTS', 'EMA_10_PTS',
        'EMA_5_REB', 'EMA_5_AST', 'EMA_5_MIN_NUMERIC',

        # Volatility
        'STD_5_PTS', 'STD_10_PTS', 'STD_5_REB', 'STD_5_AST',
        'PTS_CV', 'PTS_RANGE_5',

        # Trends
        'PTS_TREND', 'REB_TREND', 'AST_TREND',
        'PTS_RECENT_TREND', 'PTS_ACCEL',

        # Schedule
        'DAYS_REST', 'B2B', 'EXTENDED_REST', 'IS_HOME',

        # Momentum
        'WIN_STREAK', 'LOSS_STREAK', 'RECENT_WIN_PCT',

        # Role
        'MIN_CONSISTENCY', 'USAGE_PROXY', 'SHOT_VOLUME_TREND',

        # Hot/cold
        'PTS_ZSCORE', 'IS_HOT', 'IS_COLD', 'REVERSION_FACTOR',

        # Season
        'SEASON_PHASE', 'GAME_NUM',

        # Opponent
        'OPP_DEF_RATING_NORM', 'OPP_PACE_NORM', 'OPP_ELITE_DEF', 'OPP_WEAK_DEF', 'OPP_DEF_RATING_RANK',

        # Pace-adjusted
        'PTS_PACE_ADJ', 'REB_PACE_ADJ', 'AST_PACE_ADJ',

        # Efficiency
        'ROLL_5_TS_PCT', 'ROLL_5_EFG_PCT', 'ROLL_5_FANTASY_PTS',
        'ROLL_5_PRA', 'ROLL_10_PRA',

        # Injuries
        'TEAM_INJURIES_OUT', 'OPP_INJURIES_OUT', 'INJURY_USAGE_BOOST',

        # Interactions
        'B2B_VS_ELITE', 'HOT_VS_WEAK', 'RESTED_HOME',

        # VS opponent
        'VS_OPP_AVG_PTS', 'VS_OPP_AVG_REB', 'VS_OPP_AVG_AST', 'VS_OPP_GAMES',

        # Position
        'POSITION_ORD', 'POSITION_x_OPP_DEF', 'POSITION_x_OPP_PACE',
    ]

    def __init__(self, use_stacking=True):
        """
        Initialize enhanced predictor.

        Args:
            use_stacking: Whether to use stacking ensemble (recommended)
        """
        self.use_stacking = use_stacking
        self.models = {}
        self.scalers = {}
        self.feature_names = self.FEATURE_NAMES.copy()
        self.recent_averages = {}
        self.training_stats = {}
        self.feature_importance = {}
        self.last_game_date = None
        self.games_trained_on = 0
        self.probability_calibrator = {}  # Isotonic calibration data
        self.base_model_specs = None  # For custom stacking

    def _create_base_models(self):
        """Create base models for stacking ensemble."""
        models = []

        # Random Forest - good for capturing non-linear patterns
        models.append((
            'rf',
            RandomForestRegressor(
                n_estimators=150,
                max_depth=10,
                min_samples_split=5,
                min_samples_leaf=3,
                max_features='sqrt',
                random_state=42,
                n_jobs=-1
            )
        ))

        # XGBoost - excellent gradient boosting
        if XGB_AVAILABLE:
            models.append((
                'xgb',
                xgb.XGBRegressor(
                    n_estimators=150,
                    max_depth=6,
                    learning_rate=0.08,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    reg_alpha=0.1,
                    reg_lambda=1.0,
                    random_state=42,
                    verbosity=0
                )
            ))

        # LightGBM - fast and accurate
        if LGB_AVAILABLE:
            models.append((
                'lgb',
                lgb.LGBMRegressor(
                    n_estimators=150,
                    max_depth=6,
                    learning_rate=0.08,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    reg_alpha=0.1,
                    reg_lambda=1.0,
                    random_state=42,
                    verbose=-1
                )
            ))

        # HistGradientBoosting - sklearn's fast GB
        if HIST_GB_AVAILABLE:
            models.append((
                'histgb',
                HistGradientBoostingRegressor(
                    max_iter=150,
                    max_depth=6,
                    learning_rate=0.08,
                    l2_regularization=1.0,
                    random_state=42
                )
            ))

        # Gradient Boosting fallback
        if not XGB_AVAILABLE and not LGB_AVAILABLE:
            models.append((
                'gb',
                GradientBoostingRegressor(
                    n_estimators=150,
                    max_depth=5,
                    learning_rate=0.08,
                    subsample=0.8,
                    random_state=42
                )
            ))

        return models

    def _create_stacking_model(self):
        """Create stacking ensemble with meta-learner."""
        base_models = self._create_base_models()

        # Ridge regression as meta-learner (robust, prevents overfitting)
        meta_learner = Ridge(alpha=1.0)

        stacking = StackingRegressor(
            estimators=base_models,
            final_estimator=meta_learner,
            cv=5,
            n_jobs=-1,
            passthrough=True  # Include original features
        )

        return stacking

    def _fit_stacking_with_weights(self, base_models, meta_learner, X, y, weights):
        """Custom stacking that properly passes sample_weight through CV (Improvement #2)."""
        tscv = TimeSeriesSplit(n_splits=5)
        meta_features = np.full((len(y), len(base_models)), np.nan)

        for train_idx, val_idx in tscv.split(X):
            X_train, X_val = X[train_idx], X[val_idx]
            y_train, w_train = y[train_idx], weights[train_idx]

            for i, (name, model) in enumerate(base_models):
                cloned = sklearn_clone(model)
                try:
                    cloned.fit(X_train, y_train, sample_weight=w_train)
                except TypeError:
                    cloned.fit(X_train, y_train)
                meta_features[val_idx, i] = cloned.predict(X_val)

        # Only use rows that have all predictions (from CV folds)
        valid = ~np.isnan(meta_features).any(axis=1)
        if valid.sum() < 15:
            # Fallback: just use the first base model
            base_models[0][1].fit(X, y, sample_weight=weights)
            return base_models[0][1]

        # Fit meta-learner on OOF predictions + original features (passthrough)
        meta_X = np.column_stack([meta_features[valid], X[valid]])
        meta_learner.fit(meta_X, y[valid], sample_weight=weights[valid])

        # Refit all base models on full data with weights
        fitted_base = []
        for name, model in base_models:
            cloned = sklearn_clone(model)
            try:
                cloned.fit(X, y, sample_weight=weights)
            except TypeError:
                cloned.fit(X, y)
            fitted_base.append((name, cloned))

        # Return a wrapper that chains base predictions → meta prediction
        class WeightedStackingModel:
            def __init__(self, base, meta, n_features):
                self.base_models_ = base
                self.meta_learner_ = meta
                self.n_features_ = n_features
                self.estimators_ = base  # For compatibility with feature importance extraction

            def predict(self, X):
                base_preds = np.column_stack([m.predict(X) for _, m in self.base_models_])
                meta_X = np.column_stack([base_preds, X])
                return self.meta_learner_.predict(meta_X)

            def fit(self, X, y, **kwargs):
                pass  # Already fitted

        return WeightedStackingModel(fitted_base, meta_learner, X.shape[1])

    def train(self, df, stats=['PTS', 'REB', 'AST', 'PRA']):
        """
        Train models on player data with weighted stacking and probability calibration.
        """
        # Prepare features — also include new target-encoded features
        extra_features = ['OPP_ENC_PTS', 'OPP_ENC_REB', 'OPP_ENC_AST']
        all_feature_names = self.FEATURE_NAMES + [f for f in extra_features if f not in self.FEATURE_NAMES]
        feature_cols = [f for f in all_feature_names if f in df.columns]

        if len(feature_cols) < 20:
            print(f"Warning: Only {len(feature_cols)} features available")

        # Clean data
        df_clean = df.dropna(subset=feature_cols + stats)

        # Filter low-minute games
        if 'MIN_NUMERIC' in df_clean.columns:
            avg_min = df_clean['MIN_NUMERIC'].mean()
            min_threshold = max(12, avg_min * 0.4)
            df_clean = df_clean[df_clean['MIN_NUMERIC'] >= min_threshold]

        if len(df_clean) < 25:
            print(f"Warning: Only {len(df_clean)} games available for training")
            if len(df_clean) < 15:
                return False

        print(f"\n🤖 Training enhanced models on {len(df_clean)} games with {len(feature_cols)} features...")

        # Extract features
        X = df_clean[feature_cols].values
        X = np.nan_to_num(X, nan=0, posinf=0, neginf=0)

        # Use RobustScaler (handles outliers better)
        self.scalers['features'] = RobustScaler()
        X_scaled = self.scalers['features'].fit_transform(X)

        # Recency weights (exponential decay)
        n_games = len(df_clean)
        recency_weights = np.exp(np.linspace(-1, 0, n_games))
        recency_weights = recency_weights / recency_weights.sum() * n_games

        tscv = TimeSeriesSplit(n_splits=5)

        for stat in stats:
            if stat not in df_clean.columns:
                continue

            y = df_clean[stat].values

            # --- Weighted Stacking (Improvement #2) ---
            if self.use_stacking:
                base_models = self._create_base_models()
                meta_learner = Ridge(alpha=1.0)
                model = self._fit_stacking_with_weights(
                    base_models, meta_learner, X_scaled, y, recency_weights
                )
            else:
                model = self._create_base_models()[0][1]
                model.fit(X_scaled, y, sample_weight=recency_weights)

            # Cross-validation score (with weights)
            try:
                cv_scores = []
                for train_idx, val_idx in tscv.split(X_scaled):
                    fold_model = sklearn_clone(self._create_base_models()[0][1])
                    fold_model.fit(X_scaled[train_idx], y[train_idx],
                                   sample_weight=recency_weights[train_idx])
                    fold_pred = fold_model.predict(X_scaled[val_idx])
                    fold_mae = mean_absolute_error(y[val_idx], fold_pred)
                    cv_scores.append(-fold_mae)

                mae = -np.mean(cv_scores)
                mae_std = np.std(cv_scores)
                print(f"  {stat}: CV MAE = {mae:.2f} (±{mae_std:.2f})")
                self.training_stats[stat] = {'cv_mae': mae, 'cv_std': mae_std, 'n_games': len(df_clean)}
            except Exception as e:
                print(f"  {stat}: CV failed - {e}")

            self.models[stat] = model

            # --- Probability Calibration (Improvement #5) ---
            self._train_probability_calibrator(X_scaled, y, recency_weights, stat, tscv)

            # Feature importance
            try:
                if hasattr(model, 'estimators_'):
                    rf_model = [est for name, est in model.estimators_ if name == 'rf'][0]
                    importance = rf_model.feature_importances_
                elif hasattr(model, 'feature_importances_'):
                    importance = model.feature_importances_
                else:
                    importance = None
                if importance is not None:
                    self.feature_importance[stat] = dict(zip(feature_cols, importance))
            except:
                pass

        # Store recent averages
        self._update_recent_averages(df_clean, stats)

        # Update metadata
        self.feature_names = feature_cols
        self.last_game_date = df_clean['GAME_DATE'].max().strftime('%Y-%m-%d') if 'GAME_DATE' in df_clean.columns else None
        self.games_trained_on = len(df_clean)

        return True

    def _train_probability_calibrator(self, X, y, weights, stat, tscv):
        """Train isotonic regression for calibrated probabilities."""
        oof_preds = np.full(len(y), np.nan)
        for train_idx, val_idx in tscv.split(X):
            fold_model = sklearn_clone(self._create_base_models()[0][1])
            try:
                fold_model.fit(X[train_idx], y[train_idx], sample_weight=weights[train_idx])
            except TypeError:
                fold_model.fit(X[train_idx], y[train_idx])
            oof_preds[val_idx] = fold_model.predict(X[val_idx])

        valid_mask = ~np.isnan(oof_preds)
        if valid_mask.sum() < 30:
            return

        preds = oof_preds[valid_mask]
        actuals = y[valid_mask]
        std_estimate = np.std(actuals - preds) or 1.0

        z_scores_all, outcomes_all = [], []
        for i in range(len(preds)):
            for offset in np.linspace(-2 * std_estimate, 2 * std_estimate, 9):
                line = preds[i] + offset
                z = (line - preds[i]) / (std_estimate + 0.1)
                z_scores_all.append(z)
                outcomes_all.append(1 if actuals[i] > line else 0)

        raw_prob = 1 - stats.norm.cdf(np.array(z_scores_all))
        calibrator = IsotonicRegression(y_min=0.02, y_max=0.98, out_of_bounds='clip')
        calibrator.fit(raw_prob, np.array(outcomes_all))
        self.probability_calibrator[stat] = {'calibrator': calibrator, 'std_estimate': std_estimate}

    def _update_recent_averages(self, df, stats):
        """Update recent averages from latest data."""
        for stat in stats:
            if stat in df.columns:
                self.recent_averages[stat] = df[stat].tail(10).mean()

        # Also compute weighted recent average (more weight on very recent)
        for stat in stats:
            if stat in df.columns:
                recent = df[stat].tail(10).values
                weights = np.exp(np.linspace(-1, 0, len(recent)))
                self.recent_averages[f'{stat}_weighted'] = np.average(recent, weights=weights)

    def predict(self, features_df, return_uncertainty=False):
        """
        Make predictions for all trained stats.

        Args:
            features_df: DataFrame with features for prediction
            return_uncertainty: If True, also return uncertainty estimates

        Returns:
            Dict of predictions (and uncertainty if requested)
        """
        if not self.models:
            return {}

        # Prepare features
        feature_values = []
        for f in self.feature_names:
            if f in features_df.columns:
                val = features_df[f].values[0]
                feature_values.append(0 if pd.isna(val) else val)
            else:
                feature_values.append(0)

        X = np.array([feature_values])
        X = np.nan_to_num(X, nan=0, posinf=0, neginf=0)
        X_scaled = self.scalers['features'].transform(X)

        predictions = {}
        uncertainties = {}

        for stat, model in self.models.items():
            # Get raw prediction
            raw_pred = model.predict(X_scaled)[0]

            # Smart bias correction
            if stat in self.recent_averages:
                recent_avg = self.recent_averages[stat]
                weighted_avg = self.recent_averages.get(f'{stat}_weighted', recent_avg)

                # Adaptive correction based on prediction vs recent
                diff_pct = (raw_pred - recent_avg) / (recent_avg + 0.1)

                if abs(diff_pct) > 0.2:
                    # Large deviation - blend more with recent
                    correction = 0.35
                elif abs(diff_pct) > 0.1:
                    # Moderate deviation
                    correction = 0.25
                else:
                    # Small deviation - trust ML more
                    correction = 0.15

                # Asymmetric correction (be more conservative on highs)
                if raw_pred > weighted_avg:
                    correction *= 1.4  # More correction for high predictions

                pred = (1 - correction) * raw_pred + correction * weighted_avg
            else:
                pred = raw_pred

            predictions[stat] = round(pred, 1)

            # Uncertainty estimation
            if return_uncertainty:
                uncertainty = self._estimate_uncertainty(model, X_scaled, stat)
                uncertainties[stat] = uncertainty

        if return_uncertainty:
            return predictions, uncertainties
        return predictions

    def _estimate_uncertainty(self, model, X_scaled, stat):
        """Estimate prediction uncertainty using multiple methods."""
        uncertainty = {}

        # Method 1: Training CV error as baseline
        if stat in self.training_stats:
            uncertainty['cv_mae'] = self.training_stats[stat]['cv_mae']
            uncertainty['cv_std'] = self.training_stats[stat]['cv_std']

        # Method 2: Tree-based variance (for RF/stacking with RF)
        try:
            if self.use_stacking and hasattr(model, 'estimators_'):
                rf_model = [est for name, est in model.estimators_ if name == 'rf'][0]
            elif hasattr(model, 'estimators_'):
                rf_model = model
            else:
                rf_model = None

            if rf_model is not None:
                tree_preds = np.array([tree.predict(X_scaled)[0] for tree in rf_model.estimators_])
                uncertainty['tree_mean'] = tree_preds.mean()
                uncertainty['tree_std'] = tree_preds.std()
                uncertainty['tree_q25'] = np.percentile(tree_preds, 25)
                uncertainty['tree_q75'] = np.percentile(tree_preds, 75)
        except:
            pass

        # Combined uncertainty estimate
        if 'tree_std' in uncertainty and 'cv_mae' in uncertainty:
            uncertainty['combined_std'] = 0.5 * uncertainty['tree_std'] + 0.5 * uncertainty['cv_mae']
        elif 'tree_std' in uncertainty:
            uncertainty['combined_std'] = uncertainty['tree_std']
        elif 'cv_mae' in uncertainty:
            uncertainty['combined_std'] = uncertainty['cv_mae']
        else:
            uncertainty['combined_std'] = 5.0  # Default fallback

        return uncertainty

    def get_confidence(self, df, stat, prediction):
        """
        Get confidence interval for a prediction.

        Returns dict with: low, high, confidence score
        """
        # Get recent volatility
        if stat in df.columns:
            recent_std = df[stat].tail(10).std()
            overall_std = df[stat].std()
        else:
            recent_std = 5.0
            overall_std = 5.0

        # Blend recent and overall (recent matters more)
        combined_std = 0.6 * recent_std + 0.4 * overall_std

        # Training uncertainty
        cv_mae = self.training_stats.get(stat, {}).get('cv_mae', 5.0)

        # Final uncertainty estimate
        total_std = np.sqrt(combined_std**2 + cv_mae**2) / np.sqrt(2)

        # Confidence interval (approximately 80%)
        low = prediction - 1.3 * total_std
        high = prediction + 1.3 * total_std

        # Confidence score (higher std = lower confidence)
        confidence = min(95, max(55, 100 - total_std * 2.5))

        return {
            'low': round(low, 1),
            'high': round(high, 1),
            'confidence': round(confidence, 0),
            'std': round(total_std, 2)
        }

    def get_probability_over(self, prediction, line, stat, df=None):
        """
        Calculate calibrated probability of going OVER the line.
        Uses isotonic calibration when available, falls back to normal CDF.
        """
        # Get uncertainty
        if stat in self.training_stats:
            std = self.training_stats[stat]['cv_mae']
        else:
            std = 5.0

        if df is not None and stat in df.columns:
            recent_std = df[stat].tail(10).std()
            std = 0.6 * recent_std + 0.4 * std

        # Z-score and raw probability
        z = (line - prediction) / (std + 0.1)
        raw_prob_over = 1 - stats.norm.cdf(z)

        # --- Isotonic Calibration (Improvement #5) ---
        if stat in self.probability_calibrator and 'calibrator' in self.probability_calibrator[stat]:
            try:
                calibrated = self.probability_calibrator[stat]['calibrator'].predict([raw_prob_over])[0]
                return round(calibrated * 100, 1)
            except Exception:
                pass

        # Fallback: slight regression toward 50%
        prob_over = 0.85 * raw_prob_over + 0.15 * 0.5
        return round(prob_over * 100, 1)

    def get_feature_importance(self, stat, top_n=15):
        """Get top N most important features for a stat."""
        if stat not in self.feature_importance:
            return None

        importance = self.feature_importance[stat]
        sorted_importance = sorted(importance.items(), key=lambda x: x[1], reverse=True)
        return sorted_importance[:top_n]

    def save(self, player_name):
        """Save model to disk."""
        filename = Path('models') / f"{player_name.replace(' ', '_').lower()}_enhanced.pkl"
        filename.parent.mkdir(exist_ok=True)

        save_data = {
            'models': self.models,
            'scalers': self.scalers,
            'feature_names': self.feature_names,
            'recent_averages': self.recent_averages,
            'training_stats': self.training_stats,
            'feature_importance': self.feature_importance,
            'last_game_date': self.last_game_date,
            'games_trained_on': self.games_trained_on,
            'use_stacking': self.use_stacking,
            'probability_calibrator': getattr(self, 'probability_calibrator', {}),
        }

        joblib.dump(save_data, filename)
        print(f"💾 Saved enhanced model to {filename}")

    def load(self, filepath):
        """Load model from disk."""
        try:
            data = joblib.load(filepath)
            self.models = data['models']
            self.scalers = data['scalers']
            self.feature_names = data['feature_names']
            self.recent_averages = data['recent_averages']
            self.training_stats = data.get('training_stats', {})
            self.feature_importance = data.get('feature_importance', {})
            self.last_game_date = data.get('last_game_date')
            self.games_trained_on = data.get('games_trained_on', 0)
            self.use_stacking = data.get('use_stacking', True)
            self.probability_calibrator = data.get('probability_calibrator', {})
            print(f"📂 Loaded enhanced model from {filepath}")
            return True
        except Exception as e:
            print(f"⚠️ Error loading model: {e}")
            return False


class LineEvaluatorEnhanced:
    """Enhanced line evaluator with calibrated probabilities."""

    def evaluate(self, prediction, line, stat, predictor=None, df=None):
        """
        Evaluate a betting line against prediction.

        Returns comprehensive analysis including probability.
        """
        diff = prediction - line
        diff_pct = (diff / line) * 100

        # Determine recommendation strength
        if abs(diff_pct) < 2:
            recommendation = "PASS"
            strength = "NONE"
            rating = 0
        elif abs(diff_pct) < 4:
            recommendation = "LEAN OVER" if diff > 0 else "LEAN UNDER"
            strength = "SLIGHT"
            rating = 1
        elif abs(diff_pct) < 7:
            recommendation = "OVER" if diff > 0 else "UNDER"
            strength = "MODERATE"
            rating = 2
        elif abs(diff_pct) < 12:
            recommendation = "STRONG OVER" if diff > 0 else "STRONG UNDER"
            strength = "HIGH"
            rating = 3
        else:
            recommendation = "SMASH OVER" if diff > 0 else "SMASH UNDER"
            strength = "VERY HIGH"
            rating = 4

        result = {
            'stat': stat,
            'line': line,
            'prediction': prediction,
            'difference': round(diff, 1),
            'diff_pct': round(diff_pct, 1),
            'recommendation': recommendation,
            'strength': strength,
            'rating': rating
        }

        # Add probability if predictor available
        if predictor is not None:
            prob_over = predictor.get_probability_over(prediction, line, stat, df)
            result['prob_over'] = prob_over
            result['prob_under'] = round(100 - prob_over, 1)

            # Add confidence
            confidence = predictor.get_confidence(df, stat, prediction) if df is not None else None
            if confidence:
                result['confidence'] = confidence['confidence']
                result['range_low'] = confidence['low']
                result['range_high'] = confidence['high']

        return result

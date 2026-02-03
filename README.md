# 🏀 NBA Line Evaluator

**ML-Powered Player Prop Analysis for Sports Betting**

A command-line tool that uses machine learning (Random Forest, Gradient Boosting, or Neural Networks) to predict NBA player statistics and evaluate betting lines.

---

## Features

- **Multiple ML Models**: Choose between Random Forest, Gradient Boosting, or Neural Networks
- **Live Data Scraping**: Automatically fetches current schedules, injury reports, and player stats
- **Historical Analysis**: Analyzes player performance vs specific teams, home/away splits
- **Model Persistence**: Save and improve models over time with new data
- **Line Evaluation**: Compare predictions against betting lines with confidence intervals
- **Prediction Tracking**: Logs all predictions to track accuracy over time

---

## Installation

### 1. Clone/Download the files

```bash
mkdir nba_line_evaluator
cd nba_line_evaluator
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

**Note**: TensorFlow is optional. If you don't want neural network support, you can skip it:
```bash
pip install pandas numpy requests beautifulsoup4 nba_api scikit-learn joblib
```

---

## Usage

### Interactive Mode (Recommended for beginners)

```bash
python nba_evaluator.py --interactive
# or simply
python nba_evaluator.py
```

This will guide you through:
1. Entering a player name
2. Selecting a model type
3. Entering betting lines to evaluate
4. Viewing predictions and recommendations

### Command Line Mode

**Basic prediction:**
```bash
python nba_evaluator.py --player "Nikola Jokic" --stat PTS --line 26.5
```

**Multiple lines:**
```bash
python nba_evaluator.py --player "LeBron James" --pts-line 25.5 --reb-line 7.5 --ast-line 8.5 --pra-line 42.5
```

**Use Neural Network:**
```bash
python nba_evaluator.py --player "Stephen Curry" --stat PTS --line 28.5 --model neural
```

**Force retrain model:**
```bash
python nba_evaluator.py --player "Nikola Jokic" --stat PTS --line 26.5 --retrain
```

---

## Command Line Options

| Option | Short | Description |
|--------|-------|-------------|
| `--player` | `-p` | Player name to analyze |
| `--stat` | `-s` | Stat to predict (PTS, REB, AST, PRA) |
| `--line` | `-l` | Betting line to evaluate |
| `--model` | `-m` | Model type: random_forest, gradient_boost, neural |
| `--interactive` | `-i` | Run in interactive mode |
| `--all-stats` | | Predict all stats |
| `--pts-line` | | Points line |
| `--reb-line` | | Rebounds line |
| `--ast-line` | | Assists line |
| `--pra-line` | | PRA (Points + Rebounds + Assists) line |
| `--retrain` | | Force model retraining |

---

## How It Works

### Data Collection

1. **Player Info**: Fetches player ID, team, and basic info from NBA API
2. **Game Log**: Pulls last 2-3 seasons of game-by-game statistics
3. **Schedule**: Identifies upcoming/recent games and opponents
4. **Injuries**: Scrapes injury reports from sports news sites
5. **Matchup History**: Analyzes historical performance vs specific opponents

### Feature Engineering

The model uses these features for prediction:

| Feature | Description |
|---------|-------------|
| `IS_HOME` | Home (1) or Away (0) game |
| `ROLL_5_*` | 5-game rolling average for each stat |
| `ROLL_10_*` | 10-game rolling average |
| `ROLL_20_*` | 20-game rolling average |
| `STD_10_*` | 10-game standard deviation (variance) |
| `*_TREND` | Recent trend (5-game avg minus 20-game avg) |
| `DAYS_REST` | Days since last game |
| `B2B` | Back-to-back game indicator |
| `WIN_STREAK` | Recent team win momentum |
| `INJURIES_TEAM` | Number of teammates injured |
| `INJURIES_OPP` | Number of opponent players injured |

### Model Types

1. **Random Forest** (Default)
   - Ensemble of 200 decision trees
   - Best for: General use, stable predictions
   - Pros: Fast, interpretable, handles noise well

2. **Gradient Boosting**
   - Sequential tree ensemble
   - Best for: Capturing complex patterns
   - Pros: Often more accurate, good with trends

3. **Neural Network**
   - Deep learning model (requires TensorFlow)
   - Best for: Large datasets, subtle patterns
   - Pros: Can capture non-linear relationships

### Line Evaluation

The evaluator compares your prediction to the betting line and provides:

- **Recommendation**: OVER/UNDER with strength (SLIGHT, MODERATE, HIGH)
- **Confidence %**: Based on historical variance
- **Probability**: Estimated probability of hitting OVER
- **Range**: Expected outcome range (confidence interval)

---

## Output Example

```
╔═══════════════════════════════════════════════════════════════════╗
║                    🏀 NBA LINE EVALUATOR 🏀                       ║
║              ML-Powered Player Prop Analysis                      ║
╚═══════════════════════════════════════════════════════════════════╝

============================================================
  📊 ANALYSIS: NIKOLA JOKIC
============================================================
  🎮 Matchup: DEN vs. OKC
  📍 Location: HOME
  🆚 Opponent: Oklahoma City Thunder

  📈 vs OKC History (12 games):
      Avg: 27.3 PTS | 13.1 REB | 9.8 AST

------------------------------------------------------------
  🤖 ML PREDICTIONS:
------------------------------------------------------------
      PTS: 26.4
      REB: 12.8
      AST: 9.3
      PRA: 48.5

------------------------------------------------------------
  📋 LINE EVALUATIONS:
------------------------------------------------------------

  🟢 PTS Line: 25.5
      Prediction: 26.4 (+3.5%)
      ➤ LEAN OVER (SLIGHT confidence)
      Prob Over: 58%
      Range: 21.2 - 31.6

============================================================
```

---

## Data Storage

The tool creates three directories:

```
nba_line_evaluator/
├── data/           # Cached player data
├── models/         # Saved ML models (.pkl files)
└── history/        # Prediction logs (predictions.json)
```

### Tracking Accuracy

All predictions are logged to `history/predictions.json`. You can analyze this file to track your model's accuracy over time:

```python
import json
with open('history/predictions.json') as f:
    predictions = json.load(f)
    
# After games complete, update with actual results to track hits
```

---

## Improving Model Accuracy

1. **More Data**: The model improves with more historical data
2. **Regular Retraining**: Use `--retrain` periodically to incorporate new games
3. **Experiment with Models**: Try different model types for different players
4. **Track Results**: Log actual outcomes to identify model weaknesses

---

## Limitations

- **API Rate Limits**: NBA API has rate limits; the tool includes delays
- **Injury Data**: Web scraping for injuries may be incomplete
- **Future Games**: Predictions work best for near-term games
- **External Factors**: Cannot account for player motivation, game importance, etc.

---

## Troubleshooting

**"Player not found"**
- Try the full name: "LeBron James" not "LeBron"
- Check spelling

**"Insufficient data"**
- Player needs at least 20 games for training
- Try a different season or player

**TensorFlow errors**
- Neural network is optional; use `--model random_forest` instead

**Rate limit errors**
- Wait a few minutes and try again
- The tool includes rate limiting, but heavy use may hit limits

---

## License

MIT License - Use freely for personal/educational purposes.

**⚠️ Disclaimer**: This tool is for educational and entertainment purposes only. Sports betting involves risk. Always gamble responsibly.

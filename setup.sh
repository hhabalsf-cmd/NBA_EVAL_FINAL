#!/bin/bash
# NBA Line Evaluator - Setup and Run Script

echo "🏀 NBA Line Evaluator Setup"
echo "=========================="

# Check Python version
python3 --version || { echo "❌ Python 3 required"; exit 1; }

# Create virtual environment (optional but recommended)
if [ "$1" == "--venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "✅ Virtual environment activated"
fi

# Install dependencies
echo "📥 Installing dependencies..."
pip install pandas numpy requests beautifulsoup4 lxml nba_api scikit-learn joblib --quiet

# Optional: Install TensorFlow for neural networks
if [ "$1" == "--with-tensorflow" ] || [ "$2" == "--with-tensorflow" ]; then
    echo "🧠 Installing TensorFlow (this may take a while)..."
    pip install tensorflow --quiet
fi

# Create directories
mkdir -p data models history

echo ""
echo "✅ Setup complete!"
echo ""
echo "Usage examples:"
echo "  python nba_evaluator.py --interactive"
echo "  python nba_evaluator.py --player \"Nikola Jokic\" --stat PTS --line 26.5"
echo "  python nba_evaluator.py --player \"LeBron James\" --pts-line 25.5 --reb-line 7.5"
echo ""

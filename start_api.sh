#!/bin/bash
# Start the FastAPI backend server

cd "$(dirname "$0")"

# Load .env if DATABASE_URL is not already set
if [ -z "$DATABASE_URL" ] && [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL is not set. Add it to .env or export it before running."
    exit 1
fi

echo "Starting NBA Prop Evaluator API..."
echo "API docs will be available at http://localhost:8000/api/docs"
echo ""

# Check if uvicorn is installed
if ! command -v uvicorn &> /dev/null; then
    echo "Installing API dependencies..."
    pip3 install -r api/requirements.txt
fi

# Start the server
python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8000

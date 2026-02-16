#!/bin/bash
# Start the FastAPI backend server

cd "$(dirname "$0")"
echo "Starting NBA Prop Evaluator API..."
echo "API docs will be available at http://localhost:8000/api/docs"
echo ""

# Check if uvicorn is installed
if ! command -v uvicorn &> /dev/null; then
    echo "Installing API dependencies..."
    pip install -r api/requirements.txt
fi

# Start the server
cd api
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

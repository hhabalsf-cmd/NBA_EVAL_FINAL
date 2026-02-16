#!/bin/bash
# Start the React frontend dev server

cd "$(dirname "$0")/frontend"
echo "Starting NBA Prop Evaluator Frontend..."
echo "App will be available at http://localhost:5173"
echo ""

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

# Start the dev server
npm run dev

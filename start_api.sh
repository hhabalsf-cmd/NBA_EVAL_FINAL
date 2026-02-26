#!/bin/bash
# Start the FastAPI backend server

cd "$(dirname "$0")"

# Required env var: DATABASE_URL (Supabase connection string)
# Get from: Supabase dashboard → Project Settings → Database → URI
# export DATABASE_URL="postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres"
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL is not set. See start_api.sh for instructions."
    exit 1
fi

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
python -m uvicorn main:app --workers 4 --host 0.0.0.0 --port 8000

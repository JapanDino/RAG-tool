#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
export PYTHONPATH=.
if [ ! -f backend/migrations/0001_init.sql ]; then
  echo "Migration file not found"; exit 1
fi
echo "Apply SQL migration if needed:"
echo "  psql -U rag -d rag_db -f backend/migrations/0001_init.sql"
echo "Run API:"
echo "  uvicorn backend.app.main:app --reload --port 8000"

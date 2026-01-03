#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../frontend"
if [ ! -f .env.local ]; then
  echo "NEXT_PUBLIC_API_BASE=http://localhost:8000" > .env.local
fi
echo "Install deps (first time): npm i"
echo "Dev server: npm run dev"

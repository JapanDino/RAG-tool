#!/usr/bin/env bash
set -euo pipefail
DB_HOST=${DB_HOST:-127.0.0.1}
DB_PORT=${DB_PORT:-5432}
DB_NAME=${DB_NAME:-rag_db}
DB_USER=${DB_USER:-rag}
DB_PASS=${DB_PASS:-rag_pass}
export PGPASSWORD="${DB_PASS}"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# Apply all SQL migrations in lexical order (0001_... -> 9999_...).
if [ ! -d backend/migrations ]; then
  echo "backend/migrations not found"; exit 1
fi

shopt -s nullglob
files=(backend/migrations/*.sql)
if [ "${#files[@]}" -eq 0 ]; then
  echo "No migrations found in backend/migrations"; exit 1
fi

for f in "${files[@]}"; do
  echo "Applying $f..."
  psql -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$f"
done
echo "Migrations applied."

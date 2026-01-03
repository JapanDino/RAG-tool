#!/usr/bin/env bash
set -euo pipefail
DB_HOST=${DB_HOST:-127.0.0.1}
DB_PORT=${DB_PORT:-5432}
DB_NAME=${DB_NAME:-rag_db}
DB_USER=${DB_USER:-rag}
DB_PASS=${DB_PASS:-rag_pass}
export PGPASSWORD="${DB_PASS}"
for f in backend/migrations/0001_init.sql backend/migrations/0002_vector_indexes.sql backend/migrations/0003_constraints.sql backend/migrations/0004_job_task_id.sql; do
  echo "Applying $f..."
  psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$f"
done
echo "✅ Migrations applied."

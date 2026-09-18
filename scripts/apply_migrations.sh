#!/usr/bin/env bash
set -euo pipefail
DB_HOST=${DB_HOST:-127.0.0.1}
DB_PORT=${DB_PORT:-5432}
DB_NAME=${DB_NAME:-rag_db}
DB_USER=${DB_USER:-rag}
DB_PASS=${DB_PASS:-rag_pass}
export PGPASSWORD="${DB_PASS}"

psql_base=(
  psql -v ON_ERROR_STOP=1
  -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME"
)

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

"${psql_base[@]}" <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
  filename TEXT PRIMARY KEY,
  checksum TEXT NOT NULL,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
SQL

for f in "${files[@]}"; do
  filename="$(basename "$f")"
  checksum="$(sha256sum "$f" | awk '{print $1}')"
  applied_checksum="$(
    printf "SELECT checksum FROM schema_migrations WHERE filename = :'filename';\n" \
      | "${psql_base[@]}" -At -v filename="$filename"
  )"

  if [ -n "$applied_checksum" ]; then
    if [ "$applied_checksum" != "$checksum" ]; then
      echo "Migration drift detected for $filename" >&2
      echo "The applied migration differs from the file on disk; create a new migration instead." >&2
      exit 1
    fi
    echo "Skipping $filename (already applied)."
    continue
  fi

  echo "Applying $filename..."
  {
    cat "$f"
    printf "\nINSERT INTO schema_migrations (filename, checksum) VALUES (:'migration_filename', :'migration_checksum');\n"
  } | "${psql_base[@]}" --single-transaction \
    -v migration_filename="$filename" -v migration_checksum="$checksum"
done
echo "Migrations applied."

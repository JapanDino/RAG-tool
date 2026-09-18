#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "$0")/.." && pwd)"
project="rag-tool-m05-rehearsal"
compose="$root_dir/docker-compose.rehearsal.yml"

cleanup() {
  status=$?
  trap - EXIT
  if ! docker compose --project-name "$project" --file "$compose" down \
    --volumes --remove-orphans; then
    if [ "$status" -eq 0 ]; then
      status=1
    fi
  fi
  exit "$status"
}
trap cleanup EXIT

docker info >/dev/null
docker compose --project-name "$project" --file "$compose" up \
  --detach --wait db
docker compose --project-name "$project" --file "$compose" run --rm migrate
docker compose --project-name "$project" --file "$compose" run \
  --rm --build --no-deps rehearsal

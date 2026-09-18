#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

check_runtime() {
  if [[ -n "${PYTHON:-}" ]]; then
    python_bin="$PYTHON"
  elif command -v python3 >/dev/null 2>&1; then
    python_bin="python3"
  elif command -v python >/dev/null 2>&1; then
    python_bin="python"
  else
    echo "Python 3.11+ is required." >&2
    return 1
  fi
  command -v node >/dev/null 2>&1 || {
    echo "Node.js 18.18+ is required." >&2
    return 1
  }
  command -v npm >/dev/null 2>&1 || {
    echo "npm is required." >&2
    return 1
  }

  "$python_bin" - <<'PY'
import sys

if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required")
print(f"Python {sys.version.split()[0]}")
PY

  node - <<'JS'
const [major, minor] = process.versions.node.split('.').map(Number);
if (major < 18 || (major === 18 && minor < 18)) {
  throw new Error('Node.js 18.18+ is required');
}
console.log(`Node.js ${process.versions.node}`);
JS
}

check_runtime

if [[ "${1:-}" == "--check-only" ]]; then
  exit 0
fi

"$python_bin" -m pip install --disable-pip-version-check -r requirements-dev.txt
npm ci --prefix frontend

if [[ "${1:-}" == "--with-env" ]]; then
  [[ -f backend/.env ]] || cp backend/.env.example backend/.env
  [[ -f frontend/.env.local ]] || cp frontend/.env.example frontend/.env.local
  echo "Created missing local environment files from secret-free examples."
fi

echo "Online Codex dependencies are ready."
echo "Run backend checks with: python -m pytest -q"
echo "Run frontend checks with: npm --prefix frontend run lint && npm --prefix frontend run build"

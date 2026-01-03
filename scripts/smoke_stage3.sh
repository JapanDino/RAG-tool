#!/usr/bin/env bash
set -euo pipefail
API=${API:-http://localhost:8000}
TMP=./scripts/_tmp
mkdir -p "$TMP"
echo "This is a small demo text chunk to be annotated and indexed." > "$TMP/sample.txt"

echo "Create dataset"
DS=$(curl -s -X POST "$API/datasets" -H "Content-Type: application/json" -d '{"name":"demo"}' | jq -r .id)
echo "Dataset=$DS"

echo "Upload document"
curl -s -X POST "$API/datasets/$DS/documents" -F "file=@$TMP/sample.txt" >/dev/null

echo "Index"
curl -s -X POST "$API/datasets/$DS/index" >/dev/null

echo "Annotate (apply)"
curl -s -X POST "$API/annotate/datasets/$DS?level=apply" >/dev/null

echo "Export JSONL (min_score=0)"
curl -s "$API/export/datasets/$DS?format=jsonl&min_score=0" | head -n 5

echo "Status"
curl -s "$API/datasets/$DS/status" | jq
echo "✅ Smoke done."

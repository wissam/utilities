#!/usr/bin/env bash
# Origin: /tmp/vel-1167-benchmark.sh.
# Purpose: benchmark Velcontext preflight route-adjudication latency.
# Limitations: historical issue-specific prompt and fixed local endpoint.
set -euo pipefail

set -a
# shellcheck source=/dev/null
source /home/wissam/.config/velastra/velcontext-codex.env
set +a

endpoint=http://127.0.0.1:8790/v1/preflight/codex
out=$(mktemp)
trap 'rm -f "$out"' EXIT

for i in $(seq 1 "${1:-20}"); do
  total=$(curl -sS -o "$out" -w '%{time_total}' "$endpoint" \
    -H "Authorization: Bearer $VELCONTEXT_CALLER_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "{\"prompt\":\"what about that? benchmark $i\",\"cwd\":\"/home/wissam/code/projects/ai/velastra\"}")
  jq -r --arg total "$total" '[.route_adjudication.node_id, .route_adjudication.attempts[0].latency_ms, (($total|tonumber)*1000|round)] | @tsv' "$out"
done

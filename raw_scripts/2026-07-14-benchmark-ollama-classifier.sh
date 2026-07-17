#!/usr/bin/env bash
# Origin: /tmp/benchmark-ollama-classifier.sh, created for Vellm/Velcontext.
# Purpose: compare cold and warm Ollama classifier latency across nodes.
# Limitations: fixed model, endpoints, and historical request fixture.
set -euo pipefail

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
model='qwen3.5:4b'
payload="${OLLAMA_CLASSIFIER_PAYLOAD:-${script_dir}/fixtures/2026-07-14-ollama-classifier-request.json}"

run_one() {
  local label="$1" base="$2" phase="$3" index="$4"
  local output="/tmp/ollama-bench-${label}-${phase}-${index}.json"
  local wall
  wall=$(curl -sS -o "$output" -w '%{time_total}' "$base/api/chat" \
    -H 'Content-Type: application/json' --data-binary "@$payload")
  jq -c --arg host "$label" --arg phase "$phase" --argjson run "$index" --argjson wall "$wall" \
    '{host:$host,phase:$phase,run:$run,wall_ms:($wall*1000),total_ms:(.total_duration/1000000),load_ms:(.load_duration/1000000),prompt_tokens:.prompt_eval_count,prompt_ms:(.prompt_eval_duration/1000000),output_tokens:.eval_count,output_ms:(.eval_duration/1000000),output_tps:(if .eval_duration > 0 then (.eval_count/(.eval_duration/1000000000)) else 0 end),content:.message.content}' "$output"
}

benchmark_host() {
  local label="$1" base="$2"
  curl -sS "$base/api/generate" -H 'Content-Type: application/json' \
    -d "{\"model\":\"$model\",\"keep_alive\":0}" >/dev/null
  sleep 1
  run_one "$label" "$base" cold 0
  for index in 1 2 3 4 5; do
    run_one "$label" "$base" warm "$index"
  done
}

case "${1:-all}" in
  workstation) benchmark_host workstation http://127.0.0.1:11434 ;;
  is01) benchmark_host is01 http://10.0.0.186:11434 ;;
  all)
    benchmark_host workstation http://127.0.0.1:11434
    benchmark_host is01 http://10.0.0.186:11434
    ;;
  *) echo "usage: $0 [workstation|is01|all]" >&2; exit 2 ;;
esac

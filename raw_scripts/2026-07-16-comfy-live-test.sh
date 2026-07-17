#!/usr/bin/env bash
# Origin: /tmp/comfy-live-test.sh.
# Purpose: submit a ComfyUI workflow and poll it to success/error/timeout.
# Limitations: fixed local endpoint and historical B70 checkpoint fixture.
set -euo pipefail

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
endpoint=${COMFY_ENDPOINT:-http://127.0.0.1:8188}
workflow=${COMFY_WORKFLOW:-${script_dir}/fixtures/2026-07-16-comfy-xpu-probe.json}
start_ms=$(date +%s%3N)
response=$(curl -fsS -H 'Content-Type: application/json' --data-binary "@$workflow" "$endpoint/prompt")
prompt_id=$(jq -er '.prompt_id' <<<"$response")

for _ in $(seq 1 180); do
  history=$(curl -fsS "$endpoint/history/$prompt_id")
  status=$(jq -r --arg id "$prompt_id" '.[$id].status.status_str // empty' <<<"$history")
  case "$status" in
    success)
      end_ms=$(date +%s%3N)
      jq --arg id "$prompt_id" --argjson elapsed_ms "$((end_ms - start_ms))" \
        '{elapsed_ms:$elapsed_ms,status:.[$id].status,outputs:.[$id].outputs}' <<<"$history"
      exit 0
      ;;
    error)
      jq . <<<"$history"
      exit 1
      ;;
  esac
  sleep 1
done

echo 'ComfyUI prompt timed out' >&2
exit 1

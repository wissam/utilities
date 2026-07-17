#!/usr/bin/env bash
# Origin: /tmp/VEL-1223-bench.sh.
# Purpose: collect B70/Ollama quality and performance probes for Qwen 3.6.
# Limitations: fixed host, model, context size, and historical prompts.
set -eu

host=wissam@10.0.0.186
model=qwen3.6:35b-a3b
out=/tmp/VEL-1223

# Model expansion on the local side is intentional for these fixed remote probes.
# shellcheck disable=SC2029
ssh "$host" "curl -fsS http://127.0.0.1:11434/api/show -d '{\"model\":\"$model\"}'" >"${out}-show.json"
ssh "$host" "curl -fsS http://127.0.0.1:11434/api/ps" >"${out}-ps-before.json"

run_probe() {
  name=$1
  prompt=$2
  payload=$(jq -nc --arg model "$model" --arg prompt "$prompt" '{model:$model,prompt:$prompt,stream:false,think:false,keep_alive:"15m",options:{num_ctx:8192,num_predict:192,temperature:0}}')
  printf '%s' "$payload" | ssh "$host" 'curl -fsS http://127.0.0.1:11434/api/generate -d @-' >"${out}-${name}.json"
}

run_probe concise 'In no more than 80 words, explain why evidence and recommendations should remain separate in a safety-conscious distributed AI system.'
run_probe structured 'Return JSON only with keys risk, severity, and mitigation. Scenario: a remote classifier can disappear while a request is in flight.'
run_probe code-review 'Review this Go code for its most important concurrency defect and give a minimal fix: func get(m map[string]int, k string) int { go func(){ m[k]++ }(); return m[k] }'

# shellcheck disable=SC2029
ssh "$host" "ollama stop '$model' >/dev/null"
run_probe cold 'Reply with exactly: B70 cold load complete'
ssh "$host" "curl -fsS http://127.0.0.1:11434/api/ps" >"${out}-ps-after.json"

for file in "${out}"-{concise,structured,code-review,cold}.json; do
  jq '{model,total_ms:(.total_duration/1000000),load_ms:(.load_duration/1000000),prompt_tokens:.prompt_eval_count,prompt_tok_s:(.prompt_eval_count/(.prompt_eval_duration/1000000000)),output_tokens:.eval_count,output_tok_s:(.eval_count/(.eval_duration/1000000000)),response,done_reason}' "$file"
done

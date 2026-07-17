#!/usr/bin/env bash
# Origin: /tmp/vel1155-benchmark.sh.
# Purpose: historical source-routing classifier correctness and speed probe.
# Limitations: embeds the v0/v1 label semantics and a small, superseded corpus;
# do not use its accuracy as current promotion evidence.
set -euo pipefail

model=qwen3.5:4b
base=http://127.0.0.1:11434
labels='use_deterministic_routing, prefer_repo_memory, prefer_velmemory, prefer_hot_state, ask_clarification'
system="Classify the request using deterministic signals as evidence. Return JSON only with exactly label, confidence, and reason. label must be one of: ${labels}. confidence must be high, medium, or low. Prefer the deterministic label when evidence is weak. Keep reason under 240 characters."

fixtures=$(cat <<'EOF'
memory_decision|prefer_velmemory|none|What did I decide about Velmemory authentication last month?
repo_implementation|prefer_repo_memory|none|Which files implement route adjudication and what tests cover it?
cross_context|prefer_velmemory|repo-memory|How does the current route code relate to our past architecture decision?
known_incident|prefer_velmemory|none|ssh failed: Bad owner or permissions on /etc/ssh/ssh_config.d/20-systemd-ssh-proxy.conf
targeted_fix|prefer_repo_memory|none|Fix the timeout handling in internal/adjudicator/ollama.go and update its tests.
weak_referent|prefer_hot_state|none|what about that?
personal_preference|prefer_velmemory|none|Summarize my established preference for local models and hardware spending.
blast_and_decision|prefer_velmemory|repo-memory|Check the blast radius and remember why we split velcore from velrouter.
greeting|use_deterministic_routing|none|Morning!
repo_dependency|prefer_repo_memory|none|Investigate the current package dependencies in this repository.
low_signal|use_deterministic_routing|none|hmmm
acknowledgement|use_deterministic_routing|none|good stuff
EOF
)

run_case() {
  local phase=$1 iteration=$2 id=$3 expected=$4 selected=$5 text=$6
  local user request response content parsed label confidence reason valid correct selected_json
  selected_json='[]'
  [[ "$selected" != none ]] && selected_json=$(jq -cn --arg selected "$selected" '[$selected]')
  user=$(jq -cn --arg id "$id" --arg text "$text" --argjson selected "$selected_json" '{request_id:$id,schema_version:"velastra.classifier_request.v1",classifier_kind:"source_routing",visible_text:$text,context_refs:["velcontext:project:velcontext","velcontext:routing:deterministic-source-router-v1"],signals:{cwd:"/home/wissam/code/projects/ai/velcontext",selected_profiles:[],selected_sources:$selected,degraded_sources:[],skipped_sources:[],has_question:($text|endswith("?")),has_path_like:($text|contains("/")),has_concrete_target:false,has_weak_referent:false,continuation_score:0,request_score:1,source_availability_len:3},risk_level:"low",privacy_scope:"private_local",allowed_labels:["use_deterministic_routing","prefer_repo_memory","prefer_velmemory","prefer_hot_state","ask_clarification"],fallback_label:"use_deterministic_routing",policy_version:"velcontext-route-adjudicator-v0",model_class:"llm.classifier"}')
  request=$(jq -cn --arg model "$model" --arg system "$system" --arg user "$user" '{model:$model,messages:[{role:"system",content:$system},{role:"user",content:$user}],stream:false,think:false,format:"json",keep_alive:"15m",options:{temperature:0,num_predict:160}}')
  response=$(curl -fsS "$base/api/chat" -H 'Content-Type: application/json' -d "$request")
  content=$(jq -r '.message.content // ""' <<<"$response")
  valid=false label="" confidence="" reason=""
  if parsed=$(jq -ce 'if (keys|sort)==["confidence","label","reason"] and (.label|IN("use_deterministic_routing","prefer_repo_memory","prefer_velmemory","prefer_hot_state","ask_clarification")) and (.confidence|IN("high","medium","low")) and (.reason|type=="string" and length>0 and length<=240) then . else error("invalid contract") end' <<<"$content" 2>/dev/null); then
    valid=true
    label=$(jq -r '.label' <<<"$parsed")
    confidence=$(jq -r '.confidence' <<<"$parsed")
    reason=$(jq -r '.reason' <<<"$parsed")
  fi
  correct=false
  [[ "$valid" == true && "$label" == "$expected" ]] && correct=true
  jq -cn --arg phase "$phase" --argjson iteration "$iteration" --arg id "$id" --arg expected "$expected" --arg label "$label" --arg confidence "$confidence" --arg reason "$reason" --argjson valid "$valid" --argjson correct "$correct" --argjson total_ns "$(jq '.total_duration // 0' <<<"$response")" --argjson load_ns "$(jq '.load_duration // 0' <<<"$response")" --argjson prompt_count "$(jq '.prompt_eval_count // 0' <<<"$response")" --argjson prompt_ns "$(jq '.prompt_eval_duration // 0' <<<"$response")" --argjson eval_count "$(jq '.eval_count // 0' <<<"$response")" --argjson eval_ns "$(jq '.eval_duration // 0' <<<"$response")" '{phase:$phase,iteration:$iteration,id:$id,expected:$expected,label:$label,confidence:$confidence,valid:$valid,correct:$correct,reason:$reason,total_ms:($total_ns/1000000),load_ms:($load_ns/1000000),prompt_tokens:$prompt_count,prompt_tokens_per_s:(if $prompt_ns>0 then ($prompt_count*1000000000/$prompt_ns) else 0 end),output_tokens:$eval_count,output_tokens_per_s:(if $eval_ns>0 then ($eval_count*1000000000/$eval_ns) else 0 end)}'
}

if [[ "${SKIP_CUSTOM:-0}" != 1 ]]; then
  ollama stop "$model" >/dev/null 2>&1 || true
  sleep 1
  first=$(head -n1 <<<"$fixtures")
  IFS='|' read -r id expected selected text <<<"$first"
  run_case cold 0 "$id" "$expected" "$selected" "$text"

  for iteration in 1 2; do
    while IFS='|' read -r id expected selected text; do
      run_case warm "$iteration" "$id" "$expected" "$selected" "$text"
    done <<<"$fixtures"
  done
fi

eval_file=/home/wissam/code/projects/ai/velcontext/docs/evals/codex-frames.jsonl
while IFS='|' read -r id expected text; do
  run_case existing 1 "$id" "$expected" none "$text"
done < <(jq -r '[.id,(if (.expected_selected_sources|index("velcontext.hot-state")) then "prefer_hot_state" elif (.expected_selected_sources|index("repo-memory")) then "prefer_repo_memory" elif (.expected_selected_sources|index("velmemory")) then "prefer_velmemory" else "use_deterministic_routing" end),.request.prompt] | join("|")' "$eval_file")

curl -fsS "$base/api/ps" | jq -c --arg model "$model" '{runtime:{model:$model,models:[.models[] | select(.name==$model) | {name,size,size_vram,expires_at}]}}'

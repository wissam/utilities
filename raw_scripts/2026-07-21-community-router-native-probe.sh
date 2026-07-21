#!/usr/bin/env bash
# Origin: VEL-1344 community purpose-trained router investigation.
# Purpose: replay a frozen Velastra classifier fixture through the documented
# native prompt contracts of Arch-Router and Supra-Router.
# Assumptions: curl, jq, sha256sum, and a loopback Ollama endpoint are present.
# Limitations: Arch labels are adapted through route descriptions; Supra has a
# fixed small/big taxonomy, so its output is recorded but not scored against
# Velastra source-routing labels. This is research evidence, not promotion.
set -euo pipefail

usage() {
  printf 'usage: %s --fixture PATH --output PATH --model MODEL --mode arch|supra|supra-visible [--repeats N] [--base-url URL]\n' "$0" >&2
}

fixture=
output=
model=
mode=
repeats=3
base_url=http://127.0.0.1:11434

while (($#)); do
  case "$1" in
    --fixture) fixture=${2:?}; shift 2 ;;
    --output) output=${2:?}; shift 2 ;;
    --model) model=${2:?}; shift 2 ;;
    --mode) mode=${2:?}; shift 2 ;;
    --repeats) repeats=${2:?}; shift 2 ;;
    --base-url) base_url=${2:?}; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done

[[ -f "$fixture" && -n "$output" && -n "$model" ]] || { usage; exit 2; }
[[ "$mode" == arch || "$mode" == supra || "$mode" == supra-visible ]] || { usage; exit 2; }
[[ "$repeats" =~ ^[1-9][0-9]*$ ]] || { usage; exit 2; }

fixture_sha=$(sha256sum "$fixture" | cut -d' ' -f1)
: >"$output"

arch_prompt() {
  local request=$1
  jq -cn --arg request "$request" '{
    routes: [
      {name:"use_deterministic_routing",description:"Use the deterministic source selection already present when the request needs no additional repository, durable-memory, active-frame, or clarification source."},
      {name:"prefer_repo_memory",description:"Retrieve current repository implementation evidence such as code, symbols, tests, dependencies, APIs, or blast radius."},
      {name:"prefer_velmemory",description:"Retrieve durable personal, project, decision, preference, incident, or historical memory."},
      {name:"prefer_hot_state",description:"Continue from a fresh, verified, scope-matching active context frame when its referent is resolvable."},
      {name:"ask_clarification",description:"Ask the user to clarify when the referent or intended context cannot be resolved safely."}
    ],
    conversation: $request
  } | "You are a routing assistant. Route descriptions are inside <routes></routes>.\n<routes>\n" +
      (.routes | map("- " + .name + ": " + .description) | join("\n")) +
      "\n</routes>\n<conversation>\n" + .conversation +
      "\n</conversation>\nChoose the exact route name best matching the latest user intent. Return only JSON in this form: {\"route\":\"route_name\"}. If no route applies, return {\"route\":\"other\"}."'
}

while IFS= read -r test_case; do
  id=$(jq -r '.id' <<<"$test_case")
  expected=$(jq -r '.expected_label' <<<"$test_case")
  request=$(jq -c '.request' <<<"$test_case")
  visible_text=$(jq -r '.request.visible_text' <<<"$test_case")
  for ((repeat = 1; repeat <= repeats; repeat++)); do
    if [[ "$mode" == arch ]]; then
      prompt=$(arch_prompt "$request")
      payload=$(jq -cn --arg model "$model" --arg prompt "$prompt" '{model:$model,messages:[{role:"user",content:$prompt}],stream:false,keep_alive:"15m",options:{temperature:0,num_predict:80}}')
      response=$(curl -fsS --max-time 30 "$base_url/api/chat" -H 'Content-Type: application/json' -d "$payload")
      raw=$(jq -r '.message.content // ""' <<<"$response")
      route=$(jq -Rr 'try (fromjson.route // "") catch ""' <<<"$raw")
      valid=false
      jq -e --arg route "$route" '$route | IN("use_deterministic_routing","prefer_repo_memory","prefer_velmemory","prefer_hot_state","ask_clarification","other")' <<<null >/dev/null && valid=true
    else
      supra_task=$request
      [[ "$mode" == supra-visible ]] && supra_task=$visible_text
      prompt="Task: $supra_task
Analysis: "
      payload=$(jq -cn --arg model "$model" --arg prompt "$prompt" '{model:$model,prompt:$prompt,raw:true,stream:false,keep_alive:"15m",options:{temperature:0,num_predict:128}}')
      response=$(curl -fsS --max-time 30 "$base_url/api/generate" -H 'Content-Type: application/json' -d "$payload")
      raw=$(jq -r '.response // ""' <<<"$response")
      route=$(sed -n 's/.*Route: \([^|]*\).*/\1/p' <<<"$raw" | sed 's/[[:space:]]*$//')
      valid=false
      [[ "$route" == "small model" || "$route" == "big model" ]] && valid=true
    fi
    jq -cn \
      --arg schema_version velastra.community_router_probe.v1 \
      --arg mode "$mode" --arg model "$model" --arg fixture_sha256 "$fixture_sha" \
      --arg id "$id" --arg expected_label "$expected" --arg route "$route" \
      --arg raw "$raw" --argjson repeat "$repeat" --argjson valid "$valid" \
      --argjson total_ns "$(jq '.total_duration // 0' <<<"$response")" \
      '{schema_version:$schema_version,mode:$mode,model:$model,fixture_sha256:$fixture_sha256,id:$id,repeat:$repeat,expected_label:$expected_label,native_route:$route,native_contract_valid:$valid,total_ms:($total_ns/1000000),raw_output:$raw}' \
      >>"$output"
  done
done <"$fixture"

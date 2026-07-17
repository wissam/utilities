#!/usr/bin/env bash
# Origin: /tmp/velmemory-add-deploy-smoke-principal.sh.
# Purpose: add/rotate a deployment smoke-test principal in Velmemory secrets.
# Warning: mutates a live secrets file and restarts nothing. Review deployment
# ownership and auth schema before reuse; never print the generated token.
set -euo pipefail

secrets=/etc/velmemory/velmemory-api.secrets.env
tmp=$(mktemp /etc/velmemory/velmemory-api.secrets.env.XXXXXX)
trap 'rm -f "$tmp"' EXIT

# shellcheck source=/dev/null
source "$secrets"
current=${VELMEMORY_AUTH_PRINCIPALS:-[]}
jq -e 'type == "array"' <<<"$current" >/dev/null

token=$(openssl rand -hex 32)
updated=$(jq -c --arg token "$token" '
  map(select(.caller_id != "velmemory-deployment")) + [{
    token:$token,
    caller_id:"velmemory-deployment",
    caller_type:"service",
    scopes:["memory:read","memory:write"],
    tenant_ids:["local"],
    workspace_ids:["velastra-lab"],
    user_ids:["wissam"],
    agent_ids:["codex"]
  }]
' <<<"$current")

awk '!/^VELMEMORY_AUTH_PRINCIPALS=/ && !/^VELMEMORY_DEPLOY_SMOKE_TOKEN=/' "$secrets" >"$tmp"
escaped=${updated//\\/\\\\}
escaped=${escaped//\"/\\\"}
printf 'VELMEMORY_AUTH_PRINCIPALS="%s"\n' "$escaped" >>"$tmp"
printf 'VELMEMORY_DEPLOY_SMOKE_TOKEN=%s\n' "$token" >>"$tmp"

chown --reference="$secrets" "$tmp"
chmod --reference="$secrets" "$tmp"
mv "$tmp" "$secrets"
trap - EXIT

# Report only non-secret bounds for operator evidence.
jq -c '.[] | select(.caller_id == "velmemory-deployment") | del(.token)' <<<"$updated"

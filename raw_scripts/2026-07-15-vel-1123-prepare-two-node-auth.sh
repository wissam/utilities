#!/usr/bin/env bash
# Origin: /tmp/prepare-vel1123.sh.
# Purpose: historical preparation for mutual Velcore discovery authentication.
# Warning: generates credentials and deployment configuration. Review current
# contracts, endpoints, and plaintext-dogfood policy before reuse.
set -euo pipefail

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
umask 077

workstation_to_is01=/tmp/velcore-workstation-to-is01.token
is01_to_workstation=/tmp/velcore-is01-to-workstation.token
is01_current=${VEL1123_IS01_CONFIG:-${script_dir}/fixtures/2026-07-15-is01-velcore-config.current.json}

openssl rand -hex -out "${workstation_to_is01}" 32
openssl rand -hex -out "${is01_to_workstation}" 32
truncate -s -1 "${workstation_to_is01}"
truncate -s -1 "${is01_to_workstation}"

workstation_to_is01_digest="$(sha256sum "${workstation_to_is01}")"
workstation_to_is01_digest="${workstation_to_is01_digest%% *}"
is01_to_workstation_digest="$(sha256sum "${is01_to_workstation}")"
is01_to_workstation_digest="${is01_to_workstation_digest%% *}"

jq -n --arg digest "${workstation_to_is01_digest}" \
  '{principals:[{id:"velcore.local-workstation",type:"velcore-peer",token_sha256:$digest,scopes:["control.discovery"]}]}' \
  >/tmp/is01-grpc-principals.json

jq --arg digest "${is01_to_workstation_digest}" '
  .principals = (
    [.principals[] | select(.id != "velcore.is01")] +
    [{id:"velcore.is01",type:"velcore-peer",token_sha256:$digest,scopes:["control.discovery"]}]
  )
' /home/wissam/.config/velastra/velcore/grpc-principals.json \
  >/tmp/workstation-grpc-principals.json

jq '
  .peers |= map(
    if .nodeId == "is01.van.wissam.dev" then
      . + {
        authTokenFile:"/home/wissam/.config/velastra/credentials/velcore-workstation-to-is01.token",
        allowPlaintextAuth:true
      }
    else . end
  )
' /home/wissam/.config/velastra/velcore/config.json \
  >/tmp/workstation-velcore-config.json

jq '
  .grpc.auth.principalRegistry = "/home/wissam/.config/velastra/velcore/grpc-principals.json" |
  .grpc.allowPlaintextDogfood = true |
  .peers |= map(
    if .nodeId == "local-workstation.van.wissam.dev" then
      . + {
        authTokenFile:"/home/wissam/.config/velastra/credentials/velcore-is01-to-workstation.token",
        allowPlaintextAuth:true
      }
    else . end
  )
' "$is01_current" >/tmp/is01-velcore-config.json

chmod 0600 \
  "${workstation_to_is01}" \
  "${is01_to_workstation}" \
  /tmp/is01-grpc-principals.json \
  /tmp/workstation-grpc-principals.json \
  /tmp/workstation-velcore-config.json \
  /tmp/is01-velcore-config.json

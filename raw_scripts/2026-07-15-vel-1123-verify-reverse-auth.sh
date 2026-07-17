#!/usr/bin/env bash
# Origin: /tmp/verify-is01-to-workstation.sh.
# Purpose: verify anonymous refusal and authenticated reverse Velcore identity.
# Limitations: fixed endpoint and missing historical /tmp/velcore.proto input.
set -euo pipefail

grpcurl_bin=/tmp/grpcurl-VEL-1123
target=10.0.0.160:8792
token_file="${HOME}/.config/velastra/credentials/velcore-is01-to-workstation.token"
proto_file=/tmp/velcore.proto

if [[ ! -x "${grpcurl_bin}" ]]; then
  echo "missing grpcurl verifier: ${grpcurl_bin}" >&2
  exit 1
fi
mode="$(stat -c '%a' "${token_file}")"
if [[ "${mode}" != "600" && "${mode}" != "400" ]]; then
  echo "reverse discovery token must be owner-only" >&2
  exit 1
fi

if output="$("${grpcurl_bin}" -plaintext -import-path /tmp -proto "${proto_file}" \
  -d '{}' "${target}" velastra.velcore.v1.Identity/WhoAmI 2>&1)"; then
  echo "workstation unexpectedly accepted anonymous reverse discovery" >&2
  exit 1
fi
if [[ "${output}" != *"Unauthenticated"* ]]; then
  echo "anonymous reverse discovery did not fail with Unauthenticated" >&2
  echo "${output}" >&2
  exit 1
fi

VELCORE_REVERSE_TOKEN="$(<"${token_file}")"
VELCORE_REVERSE_TOKEN="${VELCORE_REVERSE_TOKEN//$'\r'/}"
VELCORE_REVERSE_TOKEN="${VELCORE_REVERSE_TOKEN//$'\n'/}"
export VELCORE_REVERSE_TOKEN
trap 'unset VELCORE_REVERSE_TOKEN' EXIT

# grpcurl expands this environment reference because -expand-headers is set.
# shellcheck disable=SC2016
identity="$("${grpcurl_bin}" -plaintext -expand-headers \
  -H 'authorization: Bearer ${VELCORE_REVERSE_TOKEN}' \
  -import-path /tmp -proto "${proto_file}" \
  -d '{}' "${target}" velastra.velcore.v1.Identity/WhoAmI)"
node_id="$(jq -r '.nodeId // .node.nodeId // empty' <<<"${identity}")"
if [[ "${node_id}" != "local-workstation.van.wissam.dev" ]]; then
  echo "expected workstation identity, got ${node_id:-<empty>}" >&2
  exit 1
fi

printf 'reverse authenticated discovery passed: %s\n' "${node_id}"

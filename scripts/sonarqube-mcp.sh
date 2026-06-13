#!/usr/bin/env bash
set -euo pipefail

SONARQUBE_URL="${SONARQUBE_URL:-${SONAR_HOST_URL:-http://10.0.0.189:9000}}"
SONARQUBE_TOKEN="${SONARQUBE_TOKEN:-${SONAR_TOKEN:-}}"
SONAR_TOKEN_HOST="${SONAR_TOKEN_HOST:-ubuntu@10.0.0.189}"
SONAR_TOKEN_FILE="${SONAR_TOKEN_FILE:-/home/ubuntu/sonarqube-credentials.txt}"
SONAR_TOKEN_SSH_CONFIG="${SONAR_TOKEN_SSH_CONFIG:-/dev/null}"
TELEMETRY_DISABLED="${TELEMETRY_DISABLED:-true}"
SONARQUBE_LOG_TO_FILE_DISABLED="${SONARQUBE_LOG_TO_FILE_DISABLED:-true}"
SONARQUBE_MCP_PULL="${SONARQUBE_MCP_PULL:-missing}"

if [[ -z "$SONARQUBE_TOKEN" ]]; then
  SONARQUBE_TOKEN="$(ssh -F "$SONAR_TOKEN_SSH_CONFIG" "$SONAR_TOKEN_HOST" "awk -F= '/^scanner_token=/ {print \$2; exit}' '$SONAR_TOKEN_FILE'")"
fi

if [[ -z "$SONARQUBE_TOKEN" ]]; then
  echo "SONARQUBE_TOKEN is required, or fetch via SONAR_TOKEN_HOST/SONAR_TOKEN_FILE must work" >&2
  exit 2
fi

export SONARQUBE_URL
export SONARQUBE_TOKEN
export TELEMETRY_DISABLED
export SONARQUBE_LOG_TO_FILE_DISABLED

docker_pull_args=()
if [[ "$SONARQUBE_MCP_PULL" != "never" ]]; then
  docker_pull_args=(--pull="$SONARQUBE_MCP_PULL")
fi

exec docker run --init "${docker_pull_args[@]}" -i --rm \
  -e SONARQUBE_TOKEN \
  -e SONARQUBE_URL \
  -e TELEMETRY_DISABLED \
  -e SONARQUBE_LOG_TO_FILE_DISABLED \
  mcp/sonarqube

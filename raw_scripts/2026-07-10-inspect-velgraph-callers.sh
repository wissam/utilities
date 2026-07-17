#!/usr/bin/env bash
# Origin: /tmp/inspect-velgraph-callers.sh, created during Velgraph auth work.
# Purpose: inspect a caller registry while redacting bearer tokens.
# Warning: sources deployment-local environment configuration.
set -euo pipefail
set -a
# shellcheck source=/dev/null
source /etc/velgraph/velgraph.env
set +a
sed -E 's/"token"[[:space:]]*:[[:space:]]*"[^"]+"/"token":"<redacted>"/g' "$VELGRAPH_CALLER_REGISTRY"

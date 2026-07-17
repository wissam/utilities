#!/usr/bin/env bash
# Origin: /tmp/smoke-velmemory-velgraph.sh, created during integration work.
# Purpose: exercise the authenticated Velmemory-to-Velgraph read path.
# Warning: reads a runtime token from deployment secrets; never log the token.
set -euo pipefail
set -a
# shellcheck source=/dev/null
source /etc/velmemory/velmemory-api.env
# shellcheck source=/dev/null
source /etc/velmemory/velmemory-api.secrets.env
set +a
token="$(python3 -c 'import json, os; print(next(p["token"] for p in json.loads(os.environ["VELMEMORY_AUTH_PRINCIPALS"]) if "graph:read" in p.get("scopes", [])))')"
curl -fsS \
  -H "Authorization: Bearer ${token}" \
  'http://127.0.0.1:8080/v1/graph/nodes/module%3Avelmemory?edge=depends_on'

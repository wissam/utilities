#!/usr/bin/env python3
"""Sanitized historical helper for adding a Velgraph caller principal.

Origin: /tmp/add-velmemory-velgraph-principal.py.
The original embedded a specific bearer-token digest. This retained copy
requires the digest through the environment and contains no credential
material. It still mutates /etc/velgraph/callers.json directly and must be
reviewed against the current auth/deployment contract before reuse.
"""

import json
import os
from pathlib import Path

path = Path("/etc/velgraph/callers.json")
digest = os.environ["VELGRAPH_BEARER_TOKEN_SHA256"]
data = json.loads(path.read_text())
principals = data.setdefault("principals", [])
principals = [item for item in principals if item.get("id") != "velmemory-reader"]
principals.append(
    {
        "id": "velmemory-reader",
        "type": "service",
        "bearer_token_sha256": digest,
        "scopes": ["graph.read"],
    }
)
data["principals"] = principals
path.write_text(json.dumps(data, indent=2) + "\n")

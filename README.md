# AI Utilities

Reusable local helper scripts for Codex, Velastra, and operator workflows.

The goal is to avoid repeatedly generating ad-hoc scripts during sessions.
Helpers here should be safe, small, and reusable.

## Install

```sh
make install
```

This installs scripts into `~/.local/bin`.

## Linear

```sh
linear-rank-issues --team VEL --team MEM --state Todo --state Backlog --label "Early Dogfood" --limit 25
```

The script reads a Linear API token from one of:

- `LINEAR_API_KEY`
- `LINEAR_API_TOKEN`
- `~/.config/linear/token`
- `~/code/agents/codex/linear-api.txt`
- `--token-file /path/to/token`

It is read-only and prints compact ranked issue rows.

The Codex Linear MCP plugin uses its own managed authentication. That token is
not exposed to shell scripts, so this helper needs a separate local Linear API
token when run outside MCP.

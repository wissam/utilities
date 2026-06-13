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

## Velastra SonarQube

```sh
velastra-sonar-scan
```

Runs SonarQube scans for the current Velastra dogfood repos and modules,
including Go coverage generation where applicable.

The script reads configuration from:

- `SONAR_HOST_URL`, defaulting to `http://10.0.0.189:9000`
- `SONAR_TOKEN`, if set locally
- `SONAR_TOKEN_HOST`, defaulting to `ubuntu@10.0.0.189`
- `SONAR_TOKEN_FILE`, defaulting to `/home/ubuntu/sonarqube-credentials.txt`
- `VELASTRA_AI_ROOT`, defaulting to `~/code/projects/ai`
- `VELASTRA_SONAR_REPORT_DIR`, defaulting to `/tmp/velastra-sonar-scan`
- `VELASTRA_SONAR_INCLUDE_ARCHIVED`, defaulting to `false`

If `SONAR_TOKEN` is not set, the script fetches the scanner token over SSH from
the SonarQube VM credentials file. It does not store the token in this repo.

Logs, generated scanner properties, and Go test coverage logs are written under
`VELASTRA_SONAR_REPORT_DIR`.

Archived or historical projects under `VELASTRA_AI_ROOT/archive` are skipped by
default. Set `VELASTRA_SONAR_INCLUDE_ARCHIVED=true` to include them in a manual
scan.

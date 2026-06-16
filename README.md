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

## Codex Git Push

```sh
codex-git-push
codex-git-push origin main
```

Runs `git push` with `GIT_SSH_COMMAND="ssh -F /dev/null"` so Codex can push
without reading global OpenSSH config includes from `/etc/ssh/ssh_config.d`.

This exists because Codex's sandbox can expose packaged system files as
`nobody:nobody`, causing OpenSSH to reject otherwise valid global config files.
The wrapper affects only the push command it runs; it does not modify host SSH
configuration.

## Velastra SonarQube

```sh
velastra-sonar-scan
```

Runs SonarQube scans for the current Velastra dogfood code repos and modules,
including Go coverage generation where applicable. Standalone documentation,
skill, report, and historical archive repos are intentionally not part of the
default scan set.

Useful scoped runs:

```sh
velastra-sonar-scan --list
velastra-sonar-scan --dry-run --project velcontext
velastra-sonar-scan --project repo-memory
velastra-sonar-scan --project velmemory --project velcontext
velastra-sonar-scan --include-archived --project velfoundation
velastra-sonar-summary --format markdown --output /tmp/velastra-sonar-scan/summary.md
velastra-sonar-summary --format json --output /tmp/velastra-sonar-scan/summary.json
```

The script reads configuration from:

- `SONAR_HOST_URL`, defaulting to `http://10.0.0.189:9000`
- `SONAR_TOKEN`, if set locally
- `SONAR_TOKEN_HOST`, defaulting to `ubuntu@10.0.0.189`
- `SONAR_TOKEN_FILE`, defaulting to `/home/ubuntu/sonarqube-credentials.txt`
- `SONAR_TOKEN_SSH_CONFIG`, defaulting to `/dev/null`
- `VELASTRA_AI_ROOT`, defaulting to `~/code/projects/ai`
- `VELASTRA_SONAR_REPORT_DIR`, defaulting to `/tmp/velastra-sonar-scan`
- `VELASTRA_SONAR_INCLUDE_ARCHIVED`, defaulting to `false`
- `VELASTRA_SONAR_PROJECTS_FILE`, defaulting to `config/velastra-sonar-projects.tsv`

If `SONAR_TOKEN` is not set, the script fetches the scanner token over SSH from
the SonarQube VM credentials file. It does not store the token in this repo.

Logs, generated scanner properties, and Go test coverage logs are written under
`VELASTRA_SONAR_REPORT_DIR`. Each scanned git repo also gets a
`<project>.git.json` metadata file recording branch, commit, and whether the
working tree was dirty. Dirty repositories are still scanned, but the script
prints a warning so dashboard findings are not confused with committed-main
quality.

Project definitions live in `config/velastra-sonar-projects.tsv` in this repo
and are installed to `~/.local/share/velastra-sonar/projects.tsv`. The scanner
script reads that file instead of keeping the repo/module list in shell code.
Use `--projects-file` or `VELASTRA_SONAR_PROJECTS_FILE` for local experiments.

`velastra-sonar-summary` exports the current SonarQube metrics and open issue
counts for the same configured project list. It can write markdown for human
review or JSON for n8n/future velcore ingestion.

Current execution mode is manual/operator-triggered. Cron, n8n, Gitea/GitHub CI,
or future velcore/velnode dispatch should wait until the project set and
expected quality thresholds stabilize.

Archived or historical projects under `VELASTRA_AI_ROOT/archive` are skipped by
default. Standalone docs/skills/report repos such as `ai-skills`,
`hermes-skills-velastra`, `velastra-root`, and `velseed-worker-reports` are not
default Sonar targets because their findings are mostly dashboard noise. Set
`VELASTRA_SONAR_INCLUDE_ARCHIVED=true` to include archived projects in a manual
scan.

Default exclusions intentionally skip raw/archive payloads, compressed export
artifacts, generated protobuf Go files, `.repo-memory`, local virtualenvs,
coverage files, generated web build output, and dependency folders. This keeps
scans focused on maintained source instead of historical ChatGPT exports,
binary archives, generated code, or generated state.

## SonarQube MCP

```sh
sonarqube-mcp
```

Launches SonarSource's official `mcp/sonarqube` container for Codex or another
stdio MCP client.

The installed launcher buffers client stdin until the SonarQube MCP container
logs that its backend is ready. This is needed because Codex sends the MCP
`initialize` request immediately, while the official container can drop early
stdio input during backend startup.

The wrapper reads:

- `SONARQUBE_URL`, defaulting to `http://10.0.0.189:9000`
- `SONARQUBE_TOKEN`, if set locally
- `SONAR_TOKEN_HOST`, defaulting to `ubuntu@10.0.0.189`
- `SONAR_TOKEN_FILE`, defaulting to `/home/ubuntu/sonarqube-credentials.txt`
- `SONAR_TOKEN_SSH_CONFIG`, defaulting to `/dev/null`
- `TELEMETRY_DISABLED`, defaulting to `true`
- `SONARQUBE_MCP_PULL`, defaulting to `missing`
- `SONARQUBE_MCP_READY_TIMEOUT`, defaulting to `75`

If `SONARQUBE_TOKEN` is not set, the wrapper fetches the scanner token over SSH
from the SonarQube VM credentials file. It does not store the token in this repo
or in the Codex MCP config.

The default pull policy avoids checking for a new container image on every MCP
startup while still pulling the image if it is missing. Set
`SONARQUBE_MCP_PULL=always` for explicit upgrades or `SONARQUBE_MCP_PULL=never`
for the fastest local startup.

Useful local Community Build tool groups:

- Project search, issue search, rules, measures, quality-gate status, source,
  SCM info, duplications, and system status/health.
- System logs/info require SonarQube admin permissions.

Likely not useful locally or edition-dependent:

- SonarQube Cloud organization/portfolio workflows.
- Pull request and branch workflows unless the local project has branch/PR
  analysis support and data.
- Advanced context-augmentation/security tools may require mounted workspace
  data, Cloud, Enterprise, or Advanced Security features.

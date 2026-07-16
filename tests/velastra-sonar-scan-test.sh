#!/usr/bin/env bash
set -euo pipefail

if [[ "$(basename -- "$0")" == "docker" ]]; then
  printf '%s\n' "$@" > "$FAKE_DOCKER_ARGS"
  exit 0
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

SOURCE_REPO="$TMP_DIR/source"
WORKTREE="$TMP_DIR/worktree"
FAKE_BIN="$TMP_DIR/bin"
REPORT_DIR="$TMP_DIR/report"
PROJECTS_FILE="$TMP_DIR/projects.tsv"
export FAKE_DOCKER_ARGS="$TMP_DIR/docker.args"

mkdir -p "$SOURCE_REPO" "$FAKE_BIN"
git -C "$SOURCE_REPO" init -q
git -C "$SOURCE_REPO" config user.email test@example.invalid
git -C "$SOURCE_REPO" config user.name Test
printf 'fixture\n' > "$SOURCE_REPO/README.md"
git -C "$SOURCE_REPO" add README.md
git -C "$SOURCE_REPO" commit -qm fixture
git -C "$SOURCE_REPO" worktree add -qb sonar-worktree "$WORKTREE"
ln -s "$SCRIPT_DIR/velastra-sonar-scan-test.sh" "$FAKE_BIN/docker"
printf 'test-key\tTest Project\tworktree\t.\t-\tfalse\tfalse\t-\n' > "$PROJECTS_FILE"

PATH="$FAKE_BIN:$PATH" \
  SONAR_TOKEN=test-token \
  VELASTRA_AI_ROOT="$TMP_DIR" \
  "$REPO_DIR/scripts/velastra-sonar-scan.sh" \
    --projects-file "$PROJECTS_FILE" \
    --report-dir "$REPORT_DIR" \
    --project test-key >/dev/null

GIT_COMMON_DIR="$(git -C "$WORKTREE" rev-parse --path-format=absolute --git-common-dir)"
grep -Fx -- "$GIT_COMMON_DIR:$GIT_COMMON_DIR:ro" "$FAKE_DOCKER_ARGS" >/dev/null
grep -F '"git": true' "$REPORT_DIR/test-key.git.json" >/dev/null
grep -F '"branch": "sonar-worktree"' "$REPORT_DIR/test-key.git.json" >/dev/null

printf 'velastra-sonar-scan linked-worktree test: ok\n'

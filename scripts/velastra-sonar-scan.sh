#!/usr/bin/env bash
set -euo pipefail

SONAR_HOST_URL="${SONAR_HOST_URL:-http://10.0.0.189:9000}"
SONAR_TOKEN="${SONAR_TOKEN:-}"
SONAR_TOKEN_HOST="${SONAR_TOKEN_HOST:-ubuntu@10.0.0.189}"
SONAR_TOKEN_FILE="${SONAR_TOKEN_FILE:-/home/ubuntu/sonarqube-credentials.txt}"
SONAR_TOKEN_SSH_CONFIG="${SONAR_TOKEN_SSH_CONFIG:-/dev/null}"
ROOT="${VELASTRA_AI_ROOT:-/home/wissam/code/projects/ai}"
REPORT_DIR="${VELASTRA_SONAR_REPORT_DIR:-/tmp/velastra-sonar-scan}"
INCLUDE_ARCHIVED="${VELASTRA_SONAR_INCLUDE_ARCHIVED:-false}"
DRY_RUN=false
LIST_ONLY=false
PROJECT_FILTERS=()

usage() {
  cat <<'EOF'
usage: velastra-sonar-scan [options]

Run SonarQube scans for Velastra dogfood repos/modules.

options:
  --project KEY        Scan only the matching project key. Repeatable.
  --list               List configured project keys and exit.
  --dry-run            Print selected scans without running tests or scanner.
  --include-archived   Include archived historical projects for this run.
  --report-dir DIR     Write logs/generated scanner configs under DIR.
  -h, --help           Show this help.

environment:
  SONAR_HOST_URL
  SONAR_TOKEN
  SONAR_TOKEN_HOST
  SONAR_TOKEN_FILE
  SONAR_TOKEN_SSH_CONFIG
  VELASTRA_AI_ROOT
  VELASTRA_SONAR_REPORT_DIR
  VELASTRA_SONAR_INCLUDE_ARCHIVED
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      if [[ $# -lt 2 || "$2" == --* ]]; then
        echo "--project requires a project key" >&2
        exit 2
      fi
      PROJECT_FILTERS+=("$2")
      shift 2
      ;;
    --list)
      LIST_ONLY=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --include-archived)
      INCLUDE_ARCHIVED=true
      shift
      ;;
    --report-dir)
      if [[ $# -lt 2 || "$2" == --* ]]; then
        echo "--report-dir requires a directory" >&2
        exit 2
      fi
      REPORT_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

selected_project() {
  local key="$1"
  local filter

  if [[ ${#PROJECT_FILTERS[@]} -eq 0 ]]; then
    return 0
  fi
  for filter in "${PROJECT_FILTERS[@]}"; do
    if [[ "$filter" == "$key" ]]; then
      return 0
    fi
  done
  return 1
}

if [[ "$LIST_ONLY" != "true" && "$DRY_RUN" != "true" && -z "$SONAR_TOKEN" ]]; then
  SONAR_TOKEN="$(ssh -F "$SONAR_TOKEN_SSH_CONFIG" "$SONAR_TOKEN_HOST" "awk -F= '/^scanner_token=/ {print \$2; exit}' '$SONAR_TOKEN_FILE'")"
fi

if [[ "$LIST_ONLY" != "true" && "$DRY_RUN" != "true" && -z "$SONAR_TOKEN" ]]; then
  echo "SONAR_TOKEN is required, or fetch via SONAR_TOKEN_HOST/SONAR_TOKEN_FILE must work" >&2
  exit 2
fi

mkdir -p "$REPORT_DIR"

scanner() {
  local base_dir="$1"
  local config="$2"

  docker run --rm \
    -e SONAR_HOST_URL="$SONAR_HOST_URL" \
    -e SONAR_TOKEN="$SONAR_TOKEN" \
    -v "$base_dir:/usr/src:ro" \
    -v "$config:/tmp/sonar-project.properties:ro" \
    sonarsource/sonar-scanner-cli:latest \
    -Dproject.settings=/tmp/sonar-project.properties
}

run_go_tests() {
  local base_dir="$1"

  if [[ -f "$base_dir/go.mod" ]]; then
    (
      cd "$base_dir"
      go test -coverprofile=coverage.out ./...
    )
  fi
}

write_config() {
  local key="$1"
  local name="$2"
  local sources="$3"
  local tests="$4"
  local coverage="$5"
  local out="$6"

  cat > "$out" <<EOF
sonar.projectKey=$key
sonar.projectName=$name
sonar.sources=$sources
sonar.tests=$tests
sonar.test.inclusions=**/*_test.go,**/*.test.ts,**/*.test.tsx,**/*.spec.ts,**/*.spec.tsx,**/*.test.js,**/*.spec.js
sonar.exclusions=bin/**,dist/**,build/**,.repo-memory/**,.venv/**,venv/**,node_modules/**,vendor/**,coverage.out,coverage/**,.next/**,raw/**,**/raw/**,archive/**,**/archive/**,batch_outputs/**,**/batch_outputs/**,*.zip,**/*.zip,*.tar,**/*.tar,*.tar.gz,**/*.tar.gz,*.tgz,**/*.tgz,*.zst,**/*.zst,*.age,**/*.age
sonar.sourceEncoding=UTF-8
EOF

  if [[ -n "$coverage" ]]; then
    printf 'sonar.go.coverage.reportPaths=%s\n' "$coverage" >> "$out"
  fi
}

scan_project() {
  local key="$1"
  local name="$2"
  local base_dir="$3"
  local sources="$4"
  local tests="${5:-}"
  local run_tests="${6:-false}"
  local coverage=""
  local log="$REPORT_DIR/$key.log"
  local config="$REPORT_DIR/$key.properties"

  if ! selected_project "$key"; then
    return 0
  fi

  if [[ "$LIST_ONLY" == "true" ]]; then
    printf '%s\t%s\t%s\n' "$key" "$name" "$base_dir"
    return 0
  fi

  echo "==> scanning $key ($base_dir)"

  if [[ ! -d "$base_dir" ]]; then
    echo "missing base dir: $base_dir" | tee "$log"
    return 1
  fi

  if [[ "$run_tests" == "true" ]]; then
    if run_go_tests "$base_dir" >"$REPORT_DIR/$key.tests.log" 2>&1; then
      coverage="coverage.out"
    else
      echo "go tests failed for $key; scanning without coverage" | tee "$REPORT_DIR/$key.tests.failed"
      cat "$REPORT_DIR/$key.tests.log"
    fi
  fi

  write_config "$key" "$name" "$sources" "$tests" "$coverage" "$config"

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "dry-run $key"
    return 0
  fi

  if scanner "$base_dir" "$config" >"$log" 2>&1; then
    echo "ok $key"
  else
    echo "failed $key; see $log" >&2
    return 1
  fi
}

failures=0

scan_project "velmemory" "velmemory" "$ROOT/velmemory" "cmd,internal,deploy,docs,examples,pkg,proto,scripts" "cmd,internal,pkg" true || failures=$((failures + 1))
scan_project "velcontext" "velcontext" "$ROOT/velcontext" "cmd,internal,docs" "cmd,internal" true || failures=$((failures + 1))
scan_project "velseed" "velseed" "$ROOT/velseed" "cmd,internal,docs,proto,skills" "cmd,internal" true || failures=$((failures + 1))
scan_project "velastra-velcore" "velastra / velcore" "$ROOT/velastra/velcore" "." "." true || failures=$((failures + 1))
scan_project "velastra-velnode" "velastra / velnode" "$ROOT/velastra/velnode" "." "." true || failures=$((failures + 1))
scan_project "velastra-velctl" "velastra / velctl" "$ROOT/velastra/velctl" "." "." true || failures=$((failures + 1))
scan_project "velastra-velrouter" "velastra / velrouter" "$ROOT/velastra/velrouter" "." "." true || failures=$((failures + 1))
scan_project "velastra-vellm" "velastra / vellm" "$ROOT/velastra/vellm" "." "." true || failures=$((failures + 1))
scan_project "velastra-root" "velastra root docs" "$ROOT/velastra" "cmd,inbox,intent,project,proto,scripts,tasks,README.md,AUDIT.md,FOR_EVA.md" "" false || failures=$((failures + 1))
scan_project "velastra-codex-plugin" "velastra-codex-plugin" "$ROOT/velastra-codex-plugin" "." "" false || failures=$((failures + 1))
scan_project "velastra-matrix-relay" "velastra-matrix-relay" "$ROOT/velastra-matrix-relay" "." "." true || failures=$((failures + 1))
scan_project "velastrasystems" "velastrasystems" "$ROOT/velastrasystems" "src,public,index.html,vite.config.ts,tsconfig.json,tsconfig.app.json,tsconfig.node.json" "" false || failures=$((failures + 1))
scan_project "codex-dispatch" "codex-dispatch" "$ROOT/codex-dispatch" "." "" false || failures=$((failures + 1))
scan_project "ai-utilities" "ai utilities" "$ROOT/utilities" "scripts,README.md,AGENTS.md" "" false || failures=$((failures + 1))
scan_project "hermes-skills-velastra" "hermes-skills-velastra" "$ROOT/hermes-skills-velastra" "." "" false || failures=$((failures + 1))
scan_project "velmemory-openclaw" "velmemory-openclaw" "$ROOT/velmemory-openclaw" "." "" false || failures=$((failures + 1))
scan_project "ai-skills" "ai-skills" "$ROOT/ai-skills" "." "" false || failures=$((failures + 1))

if [[ "$INCLUDE_ARCHIVED" == "true" ]]; then
  scan_project "velfoundation" "velfoundation" "$ROOT/archive/velfoundation" "." "" false || failures=$((failures + 1))
  scan_project "velprime" "velprime" "$ROOT/archive/velprime" "plans,scripts,reports,README.md,VELPRIME.md" "" false || failures=$((failures + 1))
elif [[ "$LIST_ONLY" != "true" ]]; then
  echo "skip archived projects: velfoundation, velprime (set VELASTRA_SONAR_INCLUDE_ARCHIVED=true to scan)"
fi

if [[ "$LIST_ONLY" != "true" ]]; then
  echo "reports: $REPORT_DIR"
fi
exit "$failures"

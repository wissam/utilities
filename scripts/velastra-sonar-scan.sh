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
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
default_projects_file() {
  if [[ -f "$SCRIPT_DIR/../share/velastra-sonar/projects.tsv" ]]; then
    printf '%s\n' "$SCRIPT_DIR/../share/velastra-sonar/projects.tsv"
  else
    printf '%s\n' "$SCRIPT_DIR/../config/velastra-sonar-projects.tsv"
  fi
}
PROJECTS_FILE="${VELASTRA_SONAR_PROJECTS_FILE:-$(default_projects_file)}"
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
  --projects-file FILE Read project definitions from FILE.
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
  VELASTRA_SONAR_PROJECTS_FILE
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
    --projects-file)
      if [[ $# -lt 2 || "$2" == --* ]]; then
        echo "--projects-file requires a file" >&2
        exit 2
      fi
      PROJECTS_FILE="$2"
      shift 2
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

field_value() {
  local value="$1"
  if [[ "$value" == "-" ]]; then
    printf ''
  else
    printf '%s' "$value"
  fi
}

bool_true() {
  case "${1,,}" in
    1|true|yes|y) return 0 ;;
    *) return 1 ;;
  esac
}

write_git_metadata() {
  local key="$1"
  local base_dir="$2"
  local out="$REPORT_DIR/$key.git.json"
  local status branch commit dirty

  if [[ ! -d "$base_dir/.git" ]]; then
    printf '{"git":false,"dirty":null}\n' > "$out"
    return 0
  fi

  branch="$(git -C "$base_dir" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  commit="$(git -C "$base_dir" rev-parse HEAD 2>/dev/null || true)"
  status="$(git -C "$base_dir" status --porcelain=v1 2>/dev/null || true)"
  dirty=false
  if [[ -n "$status" ]]; then
    dirty=true
    echo "warning: $key has uncommitted changes; scan includes working tree" >&2
  fi

  {
    printf '{\n'
    printf '  "git": true,\n'
    printf '  "branch": "%s",\n' "$branch"
    printf '  "commit": "%s",\n' "$commit"
    printf '  "dirty": %s\n' "$dirty"
    printf '}\n'
  } > "$out"
}

if [[ "$LIST_ONLY" != "true" && "$DRY_RUN" != "true" && -z "$SONAR_TOKEN" ]]; then
  SONAR_TOKEN="$(ssh -F "$SONAR_TOKEN_SSH_CONFIG" "$SONAR_TOKEN_HOST" "awk -F= '/^scanner_token=/ {print \$2; exit}' '$SONAR_TOKEN_FILE'")"
fi

if [[ "$LIST_ONLY" != "true" && "$DRY_RUN" != "true" && -z "$SONAR_TOKEN" ]]; then
  echo "SONAR_TOKEN is required, or fetch via SONAR_TOKEN_HOST/SONAR_TOKEN_FILE must work" >&2
  exit 2
fi

mkdir -p "$REPORT_DIR"

if [[ ! -f "$PROJECTS_FILE" ]]; then
  echo "project config not found: $PROJECTS_FILE" >&2
  exit 2
fi

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
  local coverage_exclusions="$6"
  local out="$7"

  cat > "$out" <<EOF
sonar.projectKey=$key
sonar.projectName=$name
sonar.sources=$sources
sonar.tests=$tests
sonar.test.inclusions=**/*_test.go,**/*.test.ts,**/*.test.tsx,**/*.spec.ts,**/*.spec.tsx,**/*.test.js,**/*.spec.js
sonar.exclusions=bin/**,dist/**,build/**,.repo-memory/**,.venv/**,venv/**,node_modules/**,vendor/**,coverage.out,coverage/**,.next/**,raw/**,**/raw/**,archive/**,**/archive/**,batch_outputs/**,**/batch_outputs/**,*.zip,**/*.zip,*.tar,**/*.tar,*.tar.gz,**/*.tar.gz,*.tgz,**/*.tgz,*.zst,**/*.zst,*.age,**/*.age,**/*.pb.go,**/*.pb.*.go,**/internal/graph/seed.go
sonar.sourceEncoding=UTF-8
EOF

  if [[ -n "$coverage" ]]; then
    printf 'sonar.go.coverage.reportPaths=%s\n' "$coverage" >> "$out"
  fi
  if [[ -n "$coverage_exclusions" ]]; then
    printf 'sonar.coverage.exclusions=%s\n' "$coverage_exclusions" >> "$out"
  fi
}

scan_project() {
  local key="$1"
  local name="$2"
  local base_dir="$3"
  local sources="$4"
  local tests="${5:-}"
  local run_tests="${6:-false}"
  local coverage_exclusions="${7:-}"
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

  write_git_metadata "$key" "$base_dir"
  write_config "$key" "$name" "$sources" "$tests" "$coverage" "$coverage_exclusions" "$config"

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
archived_skipped=()

while IFS=$'\t' read -r key name rel_path sources tests run_tests archived coverage_exclusions; do
  if [[ -z "${key:-}" || "$key" == \#* ]]; then
    continue
  fi
  tests="$(field_value "${tests:-}")"
  coverage_exclusions="$(field_value "${coverage_exclusions:-}")"
  if bool_true "${archived:-false}" && ! bool_true "$INCLUDE_ARCHIVED"; then
    archived_skipped+=("$key")
    continue
  fi
  scan_project "$key" "$name" "$ROOT/$rel_path" "$sources" "$tests" "$run_tests" "$coverage_exclusions" || failures=$((failures + 1))
done < "$PROJECTS_FILE"

if [[ "$LIST_ONLY" != "true" && ${#archived_skipped[@]} -gt 0 ]]; then
  echo "skip archived projects: ${archived_skipped[*]} (set VELASTRA_SONAR_INCLUDE_ARCHIVED=true to scan)"
fi

if [[ "$LIST_ONLY" != "true" ]]; then
  echo "reports: $REPORT_DIR"
fi
exit "$failures"

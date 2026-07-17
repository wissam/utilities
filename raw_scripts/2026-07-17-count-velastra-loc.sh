#!/usr/bin/env bash
# Origin: /tmp/count-velastra-loc.sh, created by Codex on 2026-07-17.
# Purpose: estimate first-party Velastra production/test LOC with cloc.
# Assumptions: repositories live under the hardcoded AI root and are Git repos.
# Limitations: repository membership and copied-code provenance require manual
# review; test classification is filename/path based; this is not a release
# metric or a general-purpose workspace inventory tool.
set -euo pipefail

root=/home/wissam/code/projects/ai
repos=(
  velastra velcontracts velmemory velgraph velcontext velatlas velinbox
  velastra-codex-plugin velastra-matrix-relay
  velseed curator stackchan velastrasystems agent-editor
  agent-workbench-spike herdr-velastra-plugin codex-dispatch utilities
  ai-skills hermes-skills-velastra collab roadmap
)

printf 'repo,production,test,code_total,config_data\n'
for repo in "${repos[@]}"; do
  repo_path="$root/$repo"
  [[ -d "$repo_path/.git" ]] || continue

  list=$(mktemp)
  report=$(mktemp)
  (
    cd "$repo_path"
    git ls-files |
      awk -v root="$repo_path" '
        /(^|\/)(vendor|node_modules|third_party|3rdparty|dist|build|target|coverage|htmlcov|\.venv|venv|__pycache__|generated|artifacts)(\/|$)/ { next }
        /(^|\/)(coverage\.out|package-lock\.json|pnpm-lock\.yaml|yarn\.lock|go\.sum)$/ { next }
        /\.pb\.go$/ || /_grpc\.pb\.go$/ || /\.gen\.go$/ || /generated.*\.go$/ { next }
        /\.min\.(js|css)$/ || /\.map$/ { next }
        { print root "/" $0 }
      ' >"$list"
  )

  cloc --quiet --csv --by-file --list-file="$list" >"$report" 2>/dev/null || true
  awk -F, -v repo="$repo" '
    NR == 1 { next }
    $1 == "SUM" { next }
    NF < 5 { next }
    {
      language=$1
      path=$2
      code=$5 + 0
      if (language ~ /^(JSON|YAML|TOML|XML|INI|CSV|Properties|SVG)$/) {
        config += code
        next
      }
      if (language ~ /^(Markdown|reStructuredText|Text|TeX|AsciiDoc)$/) {
        next
      }
      total += code
      if (path ~ /_test\.go$/ || path ~ /(^|\/)tests?(\/|$)/ || path ~ /(^|\/)testdata(\/|$)/ || path ~ /(^|\/)spec(\/|$)/ || path ~ /(^|\/)__tests__(\/|$)/ || path ~ /(^|\/)[^\/]*[._-](test|spec)\.(js|jsx|ts|tsx|py|rs|cpp|cc|c)$/) {
        test += code
      } else {
        production += code
      }
    }
    END { printf "%s,%d,%d,%d,%d\n", repo, production, test, total, config }
  ' "$report"
  rm -f "$list" "$report"
done


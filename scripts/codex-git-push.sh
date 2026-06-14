#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: codex-git-push [git push args...]

Run git push from Codex while bypassing global OpenSSH config includes.

Codex's sandbox can expose packaged files under /etc/ssh as nobody:nobody,
which makes OpenSSH reject global included config files even when the real host
system is healthy. This wrapper uses ssh -F /dev/null for this push only.

Examples:
  codex-git-push
  codex-git-push origin main
  codex-git-push --tags
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

exec env GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -F /dev/null}" git push "$@"

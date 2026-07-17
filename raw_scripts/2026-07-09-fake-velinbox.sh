#!/usr/bin/env bash
# Origin: /tmp/fake-velinbox, created for VEL-1064-era wake-loop testing.
# Purpose: emulate a minimal velinbox CLI for deterministic watcher tests.
# Limitations: fixed message fixture and partial command surface.
set -Eeuo pipefail

log="${FAKE_VELINBOX_LOG:-/tmp/fake-velinbox.log}"
cmd="${1:-}"
shift || true

case "$cmd" in
  inbox)
    cat <<'JSON'
{"messages":[{"id":"vbx_test_high_direct","created_by":"wissam","priority":"high","to":["codex"],"body_preview":"please run the safe wake test","deliveries":[{"recipient_id":"codex","addressed_as":"codex","status":"unread"}],"thread_id":"vbx_test_high_direct","links":[{"type":"linear","target":"VEL-1064"}]}]}
JSON
    ;;
  get)
    cat <<'JSON'
{"id":"vbx_test_high_direct","created_by":"wissam","priority":"high","to":["codex"],"body_preview":"please run the safe wake test","body_markdown":"Please run the safe wake test.","deliveries":[{"recipient_id":"codex","addressed_as":"codex","status":"unread"}],"thread_id":"vbx_test_high_direct","links":[{"type":"linear","target":"VEL-1064"}]}
JSON
    ;;
  reply | status)
    printf '%s %s\n' "$cmd" "$*" >>"$log"
    if [[ "$*" == *"--json"* ]]; then
      printf '{}\n'
    fi
    ;;
  *)
    echo "fake-velinbox: unsupported command $cmd" >&2
    exit 2
    ;;
esac

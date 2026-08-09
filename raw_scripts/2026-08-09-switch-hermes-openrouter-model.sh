#!/usr/bin/env bash
# Origin: one-time Aria/Axiom provider migration requested on 2026-08-09.
# Purpose: install an operator-approved OpenRouter credential without printing it,
# switch Hermes' default model, clear stale per-job model pins, and restart the
# user gateway. This mutates a remote Hermes installation and is not installed.
# Assumptions: direct SSH/SCP access, a one-line key file, and existing cron IDs.

set -euo pipefail

if (( $# < 3 )); then
  echo "usage: $0 <ssh-target> <key-file> <cron-job-id>..." >&2
  exit 2
fi

target=$1
key_file=$2
shift 2

remote_secret=".hermes/.openrouter-switch.$$.tmp"

chmod 600 "$key_file"
scp -q "$key_file" "$target:$remote_secret"

ssh "$target" bash -s -- "$remote_secret" "$@" <<'REMOTE'
set -euo pipefail

secret_file=$1
shift
trap 'rm -f "$secret_file"' EXIT
chmod 600 "$secret_file"

raw=$(<"$secret_file")
case "$raw" in
  OPENROUTER_API_KEY=*) key=${raw#OPENROUTER_API_KEY=} ;;
  *) key=$raw ;;
esac
key=${key%$'\r'}
test -n "$key"

env_file="$HOME/.hermes/.env"
hermes_bin="$HOME/.local/bin/hermes"
test -x "$hermes_bin"
tmp=$(mktemp "$HOME/.hermes/.env.XXXXXX")
trap 'rm -f "$secret_file" "$tmp"' EXIT
seen=0
while IFS= read -r line || test -n "$line"; do
  case "$line" in
    OPENROUTER_API_KEY=*)
      if (( seen == 0 )); then
        printf 'OPENROUTER_API_KEY=%s\n' "$key"
        seen=1
      fi
      ;;
    *) printf '%s\n' "$line" ;;
  esac
done <"$env_file" >"$tmp"
if (( seen == 0 )); then
  printf 'OPENROUTER_API_KEY=%s\n' "$key" >>"$tmp"
fi
chmod 600 "$tmp"
mv "$tmp" "$env_file"

"$hermes_bin" config set model.provider openrouter >/dev/null
"$hermes_bin" config set model.default deepseek/deepseek-v4-flash >/dev/null
for job_id in "$@"; do
  "$hermes_bin" cron edit "$job_id" --model "" --provider "" >/dev/null
done

systemctl --user restart hermes-gateway.service

set +e
smoke_output=$(timeout 120 "$hermes_bin" --safe-mode -z 'Reply exactly: DEEPSEEK_OK' 2>&1)
smoke_rc=$?
set -e
if (( smoke_rc == 0 )) && grep -q 'DEEPSEEK_OK' <<<"$smoke_output"; then
  inference=ok
else
  inference="failed(rc=$smoke_rc)"
fi

remaining_model_pins=$(awk '/"model": "kimi-k3"/ { count++ } END { print count + 0 }' "$HOME/.hermes/cron/jobs.json")
remaining_provider_pins=$(awk '/"provider": "kimi-coding"/ { count++ } END { print count + 0 }' "$HOME/.hermes/cron/jobs.json")

printf 'host=%s\n' "$(hostname)"
printf 'provider=%s\n' "$("$hermes_bin" config get model.provider)"
printf 'model=%s\n' "$("$hermes_bin" config get model.default)"
printf 'gateway=%s\n' "$(systemctl --user is-active hermes-gateway.service)"
printf 'inference=%s\n' "$inference"
printf 'credential_entries=%s\n' "$(grep -c '^OPENROUTER_API_KEY=' "$env_file")"
printf 'credential_mode=%s\n' "$(stat -c %a "$env_file")"
printf 'cron_jobs_unpinned=%s\n' "$#"
printf 'remaining_kimi_model_pins=%s\n' "$remaining_model_pins"
printf 'remaining_kimi_provider_pins=%s\n' "$remaining_provider_pins"

test "$inference" = ok
test "$remaining_model_pins" -eq 0
test "$remaining_provider_pins" -eq 0
REMOTE

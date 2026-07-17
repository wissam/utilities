#!/usr/bin/env bash
# Origin: /tmp/install-is01-vel1123.sh.
# Purpose: historical is01 half of VEL-1123 deployment.
# Warning: replaces the active binary/config/credentials and restarts Velcore.
set -euo pipefail

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${HOME}/.local/state/velastra/backups/VEL-1123-${stamp}"
config_dir="${HOME}/.config/velastra/velcore"
credential_dir="${HOME}/.config/velastra/credentials"
binary_dir="${HOME}/.local/bin"

install -d -m 0700 "${backup_dir}" "${config_dir}" "${credential_dir}" "${binary_dir}"
cp -a "${config_dir}/config.json" "${backup_dir}/config.json"
cp -a "${binary_dir}/velcore" "${backup_dir}/velcore"

install -m 0755 /tmp/velcore-VEL-1123 "${binary_dir}/velcore.new"
install -m 0600 /tmp/is01-velcore-config.json "${config_dir}/config.json.new"
install -m 0600 /tmp/is01-grpc-principals.json "${config_dir}/grpc-principals.json.new"
install -m 0600 /tmp/velcore-is01-to-workstation.token "${credential_dir}/velcore-is01-to-workstation.token.new"

mv "${binary_dir}/velcore.new" "${binary_dir}/velcore"
mv "${config_dir}/config.json.new" "${config_dir}/config.json"
mv "${config_dir}/grpc-principals.json.new" "${config_dir}/grpc-principals.json"
mv "${credential_dir}/velcore-is01-to-workstation.token.new" "${credential_dir}/velcore-is01-to-workstation.token"

systemctl --user restart velcore.service
systemctl --user is-active --quiet velcore.service

printf '%s\n' "${backup_dir}"

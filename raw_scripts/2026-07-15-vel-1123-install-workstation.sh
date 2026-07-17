#!/usr/bin/env bash
# Origin: /tmp/install-workstation-vel1123.sh.
# Purpose: historical workstation half of VEL-1123 deployment.
# Warning: mutates active Velcore config/credentials and restarts the service.
set -euo pipefail

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${HOME}/.local/state/velastra/backups/VEL-1123-${stamp}"
config_dir="${HOME}/.config/velastra/velcore"
credential_dir="${HOME}/.config/velastra/credentials"

install -d -m 0700 "${backup_dir}" "${config_dir}" "${credential_dir}"
cp -a "${config_dir}/config.json" "${backup_dir}/config.json"
cp -a "${config_dir}/grpc-principals.json" "${backup_dir}/grpc-principals.json"

install -m 0600 /tmp/workstation-velcore-config.json "${config_dir}/config.json.new"
install -m 0600 /tmp/workstation-grpc-principals.json "${config_dir}/grpc-principals.json.new"
install -m 0600 /tmp/velcore-workstation-to-is01.token "${credential_dir}/velcore-workstation-to-is01.token.new"

mv "${config_dir}/config.json.new" "${config_dir}/config.json"
mv "${config_dir}/grpc-principals.json.new" "${config_dir}/grpc-principals.json"
mv "${credential_dir}/velcore-workstation-to-is01.token.new" "${credential_dir}/velcore-workstation-to-is01.token"

systemctl --user restart velcore.service
systemctl --user is-active --quiet velcore.service

printf '%s\n' "${backup_dir}"

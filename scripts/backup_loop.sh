#!/usr/bin/env bash
set -Eeuo pipefail

backup_dir=${BACKUP_DIR:-/backups}
retention_days=${BACKUP_RETENTION_DAYS:-14}
interval_seconds=${BACKUP_INTERVAL_SECONDS:-86400}

[[ "$retention_days" =~ ^[0-9]+$ ]] || {
  echo "BACKUP_RETENTION_DAYS must be a non-negative integer" >&2
  exit 2
}
[[ "$interval_seconds" =~ ^[1-9][0-9]*$ ]] || {
  echo "BACKUP_INTERVAL_SECONDS must be a positive integer" >&2
  exit 2
}

mkdir -p "$backup_dir"

run_backup() {
  local timestamp final_path temporary_path
  timestamp=$(date -u +%Y%m%dT%H%M%SZ)
  final_path="$backup_dir/jobradarvn-$timestamp.dump"
  temporary_path="$final_path.partial"
  trap 'rm -f "$temporary_path"' RETURN

  pg_dump --format=custom --file="$temporary_path"
  chmod 600 "$temporary_path"
  mv "$temporary_path" "$final_path"
  find "$backup_dir" -type f -name 'jobradarvn-*.dump' -mtime "+$retention_days" -delete
  trap - RETURN
  echo "Created $final_path"
}

run_backup
[[ ${BACKUP_RUN_ONCE:-false} == "true" ]] && exit 0

while sleep "$interval_seconds"; do
  run_backup
done

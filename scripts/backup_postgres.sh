#!/usr/bin/env bash
set -euo pipefail

backup_dir=${BACKUP_DIR:-backups}
retention_days=${BACKUP_RETENTION_DAYS:-14}
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
final_path="$backup_dir/jobradarvn-$timestamp.dump"
temporary_path="$final_path.partial"
umask 077
mkdir -p "$backup_dir"
trap 'rm -f "$temporary_path"' EXIT

docker compose exec -T db pg_dump \
  --username jobradarvn --dbname jobradarvn --format=custom \
  > "$temporary_path"
mv "$temporary_path" "$final_path"

find "$backup_dir" -type f -name 'jobradarvn-*.dump' -mtime "+$retention_days" -delete
trap - EXIT
echo "Created $final_path"

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
backup_path="${1:?Usage: backup.sh /absolute/path/backup.dump}"
if [[ -e "$backup_path" ]]; then
  echo 'Backup target already exists; choose a new file.' >&2
  exit 1
fi
umask 077
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup_path"
if [[ ! -s "$backup_path" ]]; then
  echo 'Backup is empty.' >&2
  exit 1
fi
echo "Backup saved: $backup_path"

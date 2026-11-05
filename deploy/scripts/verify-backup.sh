#!/usr/bin/env bash
# Restore into an isolated temporary database, never the live database.
set -euo pipefail
cd "$(dirname "$0")/../.."
backup_path="${1:?Usage: verify-backup.sh backup.dump}"
verify_database="restore_check_$(date +%s)_$$"
cleanup() {
  docker compose exec -T -e VERIFY_DATABASE="$verify_database" db sh -c 'dropdb -U "$POSTGRES_USER" --if-exists "$VERIFY_DATABASE"' >/dev/null
}
trap cleanup EXIT
docker compose exec -T -e VERIFY_DATABASE="$verify_database" db sh -c 'createdb -U "$POSTGRES_USER" "$VERIFY_DATABASE"'
docker compose exec -T -e VERIFY_DATABASE="$verify_database" db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$VERIFY_DATABASE" --no-owner --exit-on-error' < "$backup_path"
docker compose exec -T -e VERIFY_DATABASE="$verify_database" db sh -c 'psql -U "$POSTGRES_USER" -d "$VERIFY_DATABASE" -c "SELECT version_num FROM alembic_version"'
echo 'Isolated restore check passed.'

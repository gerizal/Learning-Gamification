#!/usr/bin/env bash
# Local dev PostgreSQL cluster in ./.pgdata on port 55432 (socket dir also ./.pgdata).
# Usage: scripts/dev_db.sh        -> init (if needed), start (if needed), create db, apply db/*.sql
#        scripts/dev_db.sh stop   -> stop the cluster
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PGDATA="$ROOT/.pgdata"
PORT="${PGPORT:-55432}"
DB="playclass"
export PGHOST="$PGDATA" PGPORT="$PORT" PGOPTIONS="-c client_min_messages=warning"

if [ "${1:-}" = "stop" ]; then
  if pg_ctl -D "$PGDATA" status >/dev/null 2>&1; then
    pg_ctl -D "$PGDATA" -m fast stop
  else
    echo "Postgres not running."
  fi
  exit 0
fi

if [ ! -f "$PGDATA/PG_VERSION" ]; then
  echo "Initialising cluster in $PGDATA ..."
  initdb -D "$PGDATA" -U "$(whoami)" --auth=trust --encoding=UTF8 --locale=C >/dev/null
fi

if ! pg_ctl -D "$PGDATA" status >/dev/null 2>&1; then
  echo "Starting postgres on port $PORT ..."
  pg_ctl -D "$PGDATA" -l "$PGDATA/server.log" -w \
    -o "-p $PORT -k '$PGDATA' -c listen_addresses=localhost" start
fi

if ! psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$DB'" | grep -q 1; then
  createdb "$DB"
fi

# Apply every db/NNN_*.sql in numeric/byte order (001 schema, 002 seed, 003 classroom, 004 packs, ...).
# All files are idempotent, so re-running is safe. LC_ALL=C keeps the order locale-independent.
while IFS= read -r f; do
  echo "Applying $(basename "$f")"
  psql -v ON_ERROR_STOP=1 -q -d "$DB" -f "$f"
done < <(find "$ROOT/db" -maxdepth 1 -name '*.sql' -type f | LC_ALL=C sort)

echo "Ready. DATABASE_URL=postgresql://localhost:$PORT/$DB"

#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${1:-water_quality}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCHEMA_FILE="$SCRIPT_DIR/../schema.sql"

if [ ! -f "$SCHEMA_FILE" ]; then
    echo "ERROR: schema.sql not found at $SCHEMA_FILE" >&2
    exit 1
fi

echo "==> Creating database '$DB_NAME' (if it does not exist)..."
createdb "$DB_NAME" 2>/dev/null || echo "    Database '$DB_NAME' already exists, continuing."

echo "==> Applying schema..."
psql -d "$DB_NAME" -f "$SCHEMA_FILE" -v ON_ERROR_STOP=0 2>&1 | grep -v "already exists" || true

echo "==> Verifying tables..."
TABLE_COUNT=$(psql -d "$DB_NAME" -tAc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';")
echo "    Found $TABLE_COUNT tables in '$DB_NAME'."

echo "==> Done."

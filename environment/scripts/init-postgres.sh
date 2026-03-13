#!/usr/bin/env bash
set -euo pipefail

POSTGRES_USER="${POSTGRES_USER:-familyhub}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-familyhub}"
POSTGRES_DB="${POSTGRES_DB:-familyhub}"
POSTGRES_VERSION="${POSTGRES_VERSION:-15}"
POSTGRES_CLUSTER="${POSTGRES_CLUSTER:-main}"

if ! command -v pg_ctlcluster >/dev/null 2>&1; then
  echo "pg_ctlcluster is not available. Install the Debian PostgreSQL packages first." >&2
  exit 1
fi

if ! pg_lsclusters | awk 'NR>1 {print $1":"$2":"$4}' | grep -q "^${POSTGRES_VERSION}:${POSTGRES_CLUSTER}:online$"; then
  pg_ctlcluster "${POSTGRES_VERSION}" "${POSTGRES_CLUSTER}" start
fi

su postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='${POSTGRES_USER}'\"" | grep -q 1 || \
  su postgres -c "createuser ${POSTGRES_USER}"

su postgres -c "psql -c \"ALTER USER ${POSTGRES_USER} WITH PASSWORD '${POSTGRES_PASSWORD}';\""

su postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='${POSTGRES_DB}'\"" | grep -q 1 || \
  su postgres -c "createdb -O ${POSTGRES_USER} ${POSTGRES_DB}"

echo "PostgreSQL is ready for ${POSTGRES_DB}"

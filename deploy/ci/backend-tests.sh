#!/usr/bin/env bash
# CI gate for the backend, run by Jenkinsfile.prod against the image that is about to ship.
#
#   deploy/ci/backend-tests.sh <image> <results-dir>
#
# 1. starts a throwaway PostGIS container
# 2. checks alembic has exactly one head
# 3. runs `alembic upgrade head` on an empty database (every migration must apply cleanly)
# 4. runs the pytest suite (tests/conftest.py expects test/test@localhost:5432/test_db,
#    so the test container shares the DB container's network namespace)
# JUnit XML goes to <results-dir>/pytest.xml.
set -euo pipefail

IMAGE=${1:?usage: $0 <image> <results-dir>}
RESULTS=${2:?usage: $0 <image> <results-dir>}
DB=breedly-ci-db-${BUILD_TAG:-local}-$$
DB=${DB//[^a-zA-Z0-9_.-]/-}
mkdir -p "$RESULTS"
RESULTS=$(cd "$RESULTS" && pwd)

cleanup() { docker rm -f "$DB" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "--- starting PostGIS ($DB)"
# Throwaway DB: data on tmpfs and durability off. Every test creates and drops the whole schema,
# so fsync cost dominates the run time on the Jenkins box (HDD).
docker run -d --name "$DB" \
  --tmpfs /var/lib/postgresql/data:rw,size=1g \
  -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test_db \
  postgis/postgis:15-3.3-alpine \
  -c fsync=off -c synchronous_commit=off -c full_page_writes=off >/dev/null
for _ in $(seq 1 60); do
  # pg_isready can succeed during the image's init restart; require a real query to pass twice
  if docker exec "$DB" psql -U test -d test_db -qtAc 'select 1' >/dev/null 2>&1; then
    sleep 2
    docker exec "$DB" psql -U test -d test_db -qtAc 'select 1' >/dev/null 2>&1 && break
  fi
  sleep 2
done
docker exec "$DB" psql -U test -d test_db -qtAc 'select 1' >/dev/null || { echo "PostGIS did not start"; exit 1; }
docker exec "$DB" psql -U test -d test_db -qc 'CREATE DATABASE migrate_db' >/dev/null

run_in_image() {
  docker run --rm --network "container:$DB" \
    -e TESTING=1 \
    -e SECRET_KEY=ci-only-secret-key-not-used-anywhere-else-0123456789 \
    -e BILLING_ENCRYPTION_KEY=ci-only-billing-key \
    -v "$RESULTS:/results" \
    "$@"
}

echo "--- alembic: single head"
heads=$(run_in_image -e DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/migrate_db \
  "$IMAGE" alembic heads | grep -c '(head)' || true)
if [ "$heads" != "1" ]; then
  echo "expected exactly 1 alembic head, found $heads - add a merge migration (alembic merge heads)"
  exit 1
fi

echo "--- alembic: upgrade head on an empty database"
run_in_image -e DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/migrate_db \
  "$IMAGE" alembic upgrade head

echo "--- pytest"
set +e
run_in_image -e DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/test_db \
  -e COVERAGE_FILE=/tmp/.coverage \
  "$IMAGE" sh -c "python -m pytest -q -p no:cacheprovider --no-cov --junitxml=/results/pytest.xml; rc=\$?; chown -R $(id -u):$(id -g) /results; exit \$rc"
rc=$?
set -e
exit $rc

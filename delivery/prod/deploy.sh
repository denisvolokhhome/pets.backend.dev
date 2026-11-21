#!/usr/bin/env bash
# Production deploy for one Breedly service. Runs ON prod-docker as user `breedly`,
# from /home/breedly/breedly-app (Jenkinsfile.prod copies it there).
#
#   ./deploy.sh backend  <tag>   pg_dump backup -> alembic upgrade head -> seed -> switch backend -> health check
#   ./deploy.sh frontend <tag>   switch frontend -> health check
#   ./deploy.sh rollback <backend|frontend>   go back to the tag deployed before the current one
#
# If the new container fails its health check, the previous tag is restored automatically.
# The DATABASE is not rolled back automatically: alembic runs in one transaction, so a failed
# migration leaves the schema untouched, but a successful migration followed by a failing app
# is restored from the pre-deploy dump by hand (path is printed below).
set -euo pipefail

APP_DIR=/home/breedly/breedly-app
BACKUP_DIR=/home/breedly/backups
KEEP_PREDEPLOY_BACKUPS=20
HEALTH_TIMEOUT=180
cd "$APP_DIR"

touch releases.env
COMPOSE=(docker compose -f docker-compose.prod.yml --env-file .env --env-file releases.env)

log() { printf '[deploy %s] %s\n' "$(date '+%F %T')" "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

get_tag() { grep -E "^$1=" releases.env | tail -1 | cut -d= -f2- || true; }
set_tag() {
  # $1 var, $2 value. One line per var; the value it replaces is kept as <var>_PREVIOUS.
  local var=$1 val=$2 cur prev
  cur=$(get_tag "$var"); prev=$(get_tag "${var}_PREVIOUS")
  if [ -n "$cur" ] && [ "$cur" != "$val" ]; then prev=$cur; fi
  { grep -vE "^(${var}|${var}_PREVIOUS)=" releases.env || true
    [ -n "$prev" ] && echo "${var}_PREVIOUS=${prev}"
    echo "${var}=${val}"; } > releases.env.tmp
  mv releases.env.tmp releases.env
}

wait_healthy() {
  local svc=$1 cid status waited=0
  cid=$("${COMPOSE[@]}" ps -q "$svc")
  [ -n "$cid" ] || { log "$svc has no container"; return 1; }
  while [ $waited -lt $HEALTH_TIMEOUT ]; do
    status=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" 2>/dev/null || echo missing)
    case $status in
      healthy) log "$svc is healthy"; return 0 ;;
      unhealthy|exited|dead|missing) log "$svc is $status"; docker logs --tail 50 "$cid" 2>&1 | sed 's/^/    /'; return 1 ;;
    esac
    sleep 5; waited=$((waited + 5))
  done
  log "$svc not healthy after ${HEALTH_TIMEOUT}s"; docker logs --tail 50 "$cid" 2>&1 | sed 's/^/    /'
  return 1
}

switch_service() {
  # $1 service, $2 TAG var, $3 new tag
  local svc=$1 var=$2 new=$3 old
  old=$(get_tag "$var")
  set_tag "$var" "$new"
  log "switching $svc: ${old:-<none>} -> $new"
  "${COMPOSE[@]}" up -d --no-deps "$svc"
  if wait_healthy "$svc"; then
    log "$svc $new is live"
    return 0
  fi
  if [ -n "$old" ] && [ "$old" != "$new" ]; then
    log "health check failed, rolling $svc back to $old"
    set_tag "$var" "$old"
    "${COMPOSE[@]}" up -d --no-deps "$svc"
    wait_healthy "$svc" || log "WARNING: rollback container for $svc is not healthy either"
  fi
  return 1
}

backup_db() {
  local tag=$1 file
  mkdir -p "$BACKUP_DIR"
  file="$BACKUP_DIR/predeploy-$(date +%Y%m%d-%H%M%S)-${tag}.dump"
  log "backing up database -> $file"
  "${COMPOSE[@]}" exec -T postgres pg_dump -U breedly_user -d breedly_db -Fc > "$file.partial"
  mv "$file.partial" "$file"
  log "backup size: $(du -h "$file" | cut -f1)"
  ls -1t "$BACKUP_DIR"/predeploy-*.dump 2>/dev/null | tail -n +$((KEEP_PREDEPLOY_BACKUPS + 1)) | xargs -r rm -f
  echo "$file"
}

deploy_backend() {
  local tag=$1 backup
  log "pulling backend $tag"
  BACKEND_TAG=$tag "${COMPOSE[@]}" pull backend

  log "ensuring postgres and redis are up"
  "${COMPOSE[@]}" up -d --wait postgres redis

  backup=$(backup_db "$tag")

  log "applying migrations (alembic upgrade head)"
  BACKEND_TAG=$tag "${COMPOSE[@]}" run --rm migration \
    || die "migration failed - schema unchanged (single transaction), backend still on $(get_tag BACKEND_TAG)"

  log "seeding reference data (idempotent)"
  BACKEND_TAG=$tag "${COMPOSE[@]}" run --rm seed || die "seed failed - backend still on $(get_tag BACKEND_TAG)"

  switch_service backend BACKEND_TAG "$tag" \
    || die "backend $tag failed health check and was rolled back. Migrations WERE applied; pre-deploy dump: $backup"
}

deploy_frontend() {
  local tag=$1
  log "pulling frontend $tag"
  FRONTEND_TAG=$tag "${COMPOSE[@]}" pull frontend
  switch_service frontend FRONTEND_TAG "$tag" || die "frontend $tag failed health check and was rolled back"
}

rollback() {
  local svc=$1 var prev
  case $svc in backend) var=BACKEND_TAG ;; frontend) var=FRONTEND_TAG ;; *) die "rollback backend|frontend" ;; esac
  prev=$(get_tag "${var}_PREVIOUS")
  [ -n "$prev" ] || die "no previous $svc tag recorded"
  log "rolling $svc back to $prev (database is NOT touched)"
  switch_service "$svc" "$var" "$prev" || die "rollback failed"
}

case "${1:-}" in
  backend)  [ -n "${2:-}" ] || die "usage: $0 backend <tag>";  deploy_backend "$2" ;;
  frontend) [ -n "${2:-}" ] || die "usage: $0 frontend <tag>"; deploy_frontend "$2" ;;
  rollback) rollback "${2:-}" ;;
  status)   cat releases.env; "${COMPOSE[@]}" ps ;;
  *) die "usage: $0 backend <tag> | frontend <tag> | rollback <backend|frontend> | status" ;;
esac

docker image prune -f --filter "until=168h" >/dev/null 2>&1 || true
log "done"; cat releases.env

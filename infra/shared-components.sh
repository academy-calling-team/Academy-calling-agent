#!/bin/sh
set -eu
wait_api() {
  attempt=0
  until docker exec team8-shared-api python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:18771/ready",timeout=2)' >/dev/null 2>&1; do
    attempt=$((attempt+1)); [ "$attempt" -lt 30 ] || return 1; sleep 1
  done
}
wait_worker() {
  attempt=0
  until docker exec team8-shared-api python -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:18780/docs",timeout=2)' >/dev/null 2>&1; do
    attempt=$((attempt+1)); [ "$attempt" -lt 30 ] || return 1; sleep 1
  done
}
case "${1:-status}" in
  status)
    docker ps --filter name=team8-shared --format '{{.Names}} {{.Status}}'
    wait_api && wait_worker && echo 'Shared API and voice mock worker respond.'
    ;;
  restart-worker)
    docker stop team8-shared-queue >/dev/null
    docker restart team8-shared-worker >/dev/null
    wait_worker
    docker start team8-shared-queue >/dev/null
    echo 'Mock worker and queue restarted; receipt volume kept.'
    ;;
  pause)
    docker stop team8-shared-queue >/dev/null
    echo 'Queue paused; API and worker kept.'
    ;;
  resume)
    wait_api; wait_worker
    docker start team8-shared-queue >/dev/null
    echo 'Queue resumed.'
    ;;
  *) echo 'Usage: shared-components.sh status|restart-worker|pause|resume' >&2; exit 2 ;;
esac

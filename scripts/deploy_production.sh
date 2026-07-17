#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Usage: $0 deploy <deploy-root> <release-id> | rollback <deploy-root>" >&2
  exit 2
}

compose() {
  docker compose \
    -f compose.yaml \
    -f compose.production.yaml \
    -f compose.monitoring.yaml \
    -f compose.monitoring.production.yaml \
    "$@"
}

require_free_disk() {
  local path=$1
  local minimum_mb=${MIN_FREE_DISK_MB:-10240}

  [[ "$minimum_mb" =~ ^[1-9][0-9]*$ ]] || {
    echo "MIN_FREE_DISK_MB must be a positive integer" >&2
    return 1
  }

  local available_kb
  available_kb=$(df -Pk "$path" | awk 'NR == 2 {print $4}')
  if ((available_kb < minimum_mb * 1024)); then
    echo "Insufficient disk space: need ${minimum_mb} MiB free under $path" >&2
    df -h "$path" >&2
    return 1
  fi
}

wait_for_internal_health() {
  local attempt
  for attempt in $(seq 1 60); do
    if compose exec -T api python -c \
      "import urllib.request; [urllib.request.urlopen(url, timeout=3) for url in ('http://localhost:8000/health/ready', 'http://prometheus:9090/-/ready', 'http://grafana:3000/api/health')]" \
      >/dev/null 2>&1 \
      && compose exec -T web node -e \
        "fetch('http://localhost:3000').then(r => { if (!r.ok) process.exit(1) })" \
        >/dev/null 2>&1; then
      return 0
    fi
    sleep 3
  done
  compose ps >&2
  return 1
}

activate_release() {
  local deploy_root=$1
  local release_dir=$2
  local current_link="$deploy_root/current"
  local next_link="$deploy_root/.current-next"

  ln -sfn "$release_dir" "$next_link"
  mv -Tf "$next_link" "$current_link"
}

deploy() {
  local deploy_root=$1
  local release_id=$2
  local release_dir="$deploy_root/releases/$release_id"
  local previous=""

  [[ "$release_id" =~ ^[A-Za-z0-9._-]+$ ]] || usage
  [[ -f "$release_dir/compose.yaml" ]] || usage
  [[ -f "$release_dir/compose.production.yaml" ]] || usage
  [[ -f "$release_dir/compose.monitoring.yaml" ]] || usage
  [[ -f "$release_dir/compose.monitoring.production.yaml" ]] || usage
  [[ -f "$release_dir/.env" ]] || usage
  chmod 600 "$release_dir/.env"
  mkdir -p "$deploy_root/releases"

  if [[ -L "$deploy_root/current" ]]; then
    previous=$(readlink -f "$deploy_root/current")
  fi

  cd "$release_dir"
  compose config -q
  docker image prune -f >/dev/null
  require_free_disk "$deploy_root"
  compose pull
  compose up -d --no-build --remove-orphans
  if ! wait_for_internal_health; then
    echo "Release $release_id failed internal health checks" >&2
    if [[ -n "$previous" && -d "$previous" ]]; then
      echo "Restoring $(basename "$previous")" >&2
      cd "$previous"
      compose up -d --no-build --remove-orphans
      wait_for_internal_health
      activate_release "$deploy_root" "$previous"
    fi
    return 1
  fi

  if [[ -n "$previous" && "$previous" != "$release_dir" ]]; then
    printf '%s\n' "$previous" > "$deploy_root/.previous-release"
  fi
  activate_release "$deploy_root" "$release_dir"
  echo "Activated release $release_id"
}

rollback() {
  local deploy_root=$1
  local previous_file="$deploy_root/.previous-release"
  [[ -f "$previous_file" ]] || {
    echo "No previous release is recorded" >&2
    exit 1
  }
  local previous
  previous=$(<"$previous_file")
  [[ -d "$previous" && -f "$previous/.env" ]] || {
    echo "Recorded previous release is unavailable: $previous" >&2
    exit 1
  }

  cd "$previous"
  compose config -q
  compose up -d --no-build --remove-orphans
  wait_for_internal_health
  activate_release "$deploy_root" "$previous"
  echo "Rolled back to $(basename "$previous")"
}

case ${1:-} in
  deploy)
    [[ $# -eq 3 ]] || usage
    deploy "$2" "$3"
    ;;
  rollback)
    [[ $# -eq 2 ]] || usage
    rollback "$2"
    ;;
  *) usage ;;
esac

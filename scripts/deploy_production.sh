#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Usage: $0 deploy <deploy-root> <release-id> [public|self-hosted] | rollback <deploy-root> | abort <deploy-root>" >&2
  exit 2
}

deployment_mode=public

set_deployment_mode() {
  case ${1:-public} in
    public | self-hosted) deployment_mode=${1:-public} ;;
    *) usage ;;
  esac
}

release_deployment_mode() {
  local release_dir=$1
  if [[ -f "$release_dir/.deployment-mode" ]]; then
    tr -d '[:space:]' < "$release_dir/.deployment-mode"
  else
    printf 'public'
  fi
}

compose() {
  local files=(
    -f compose.yaml
    -f compose.production.yaml
    -f compose.monitoring.yaml
    -f compose.monitoring.production.yaml
  )
  if [[ "$deployment_mode" == "self-hosted" ]]; then
    files+=(-f compose.selfhost.yaml)
  fi
  docker compose "${files[@]}" "$@"
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

require_docker_free_disk() {
  local docker_root
  docker_root=$(docker info --format '{{.DockerRootDir}}')
  [[ -n "$docker_root" && -d "$docker_root" ]] || {
    echo "Docker data root is unavailable: $docker_root" >&2
    return 1
  }
  MIN_FREE_DISK_MB=${MIN_DOCKER_FREE_DISK_MB:-${MIN_FREE_DISK_MB:-10240}} \
    require_free_disk "$docker_root"
}

wait_for_internal_health() {
  local attempts=${HEALTHCHECK_ATTEMPTS:-60}
  local interval=${HEALTHCHECK_INTERVAL_SECONDS:-3}
  [[ "$attempts" =~ ^[1-9][0-9]*$ ]] || {
    echo "HEALTHCHECK_ATTEMPTS must be a positive integer" >&2
    return 1
  }
  [[ "$interval" =~ ^[0-9]+$ ]] || {
    echo "HEALTHCHECK_INTERVAL_SECONDS must be a non-negative integer" >&2
    return 1
  }

  local attempt
  for attempt in $(seq 1 "$attempts"); do
    if compose exec -T api python -c \
      "import json, urllib.request; [urllib.request.urlopen(url, timeout=3) for url in ('http://localhost:8000/health/ready', 'http://prometheus:9090/-/ready', 'http://grafana:3000/api/health')]; assert json.load(urllib.request.urlopen('http://ml-api:8002/health', timeout=3))['model_available'] is True" \
      >/dev/null 2>&1 \
      && compose exec -T web node -e \
        "fetch('http://localhost:3000').then(r => { if (!r.ok) process.exit(1) })" \
        >/dev/null 2>&1; then
      return 0
    fi
    sleep "$interval"
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

restore_previous_or_stop() {
  local deploy_root=$1
  local failed_release=$2
  local previous=$3

  if [[ -n "$previous" && -d "$previous" ]]; then
    echo "Restoring $(basename "$previous")" >&2
    cd "$previous"
    set_deployment_mode "$(release_deployment_mode "$previous")"
    if ! compose up -d --no-build --remove-orphans; then
      echo "Previous release could not be restarted" >&2
      return 1
    fi
    if ! wait_for_internal_health; then
      echo "Previous release failed internal health checks" >&2
      return 1
    fi
    activate_release "$deploy_root" "$previous"
    return 0
  fi

  echo "No previous release exists; stopping the failed stack" >&2
  cd "$failed_release"
  set_deployment_mode "$(release_deployment_mode "$failed_release")"
  compose down --remove-orphans
}

deploy() {
  local deploy_root=$1
  local release_id=$2
  set_deployment_mode "${3:-public}"
  local release_dir="$deploy_root/releases/$release_id"
  local previous=""

  [[ "$release_id" =~ ^[A-Za-z0-9._-]+$ ]] || usage
  [[ -f "$release_dir/compose.yaml" ]] || usage
  [[ -f "$release_dir/compose.production.yaml" ]] || usage
  [[ -f "$release_dir/compose.monitoring.yaml" ]] || usage
  [[ -f "$release_dir/compose.monitoring.production.yaml" ]] || usage
  if [[ "$deployment_mode" == "self-hosted" ]]; then
    [[ -f "$release_dir/compose.selfhost.yaml" ]] || usage
  fi
  [[ -f "$release_dir/.env" ]] || usage
  chmod 600 "$release_dir/.env"
  printf '%s\n' "$deployment_mode" > "$release_dir/.deployment-mode"
  mkdir -p "$deploy_root/releases"

  if [[ -L "$deploy_root/current" ]]; then
    previous=$(readlink -f "$deploy_root/current")
  fi

  cd "$release_dir"
  compose config -q
  docker image prune -f >/dev/null
  require_free_disk "$deploy_root"
  require_docker_free_disk
  compose pull
  if ! compose up -d --no-build --remove-orphans; then
    echo "Release $release_id failed to start" >&2
    if ! restore_previous_or_stop "$deploy_root" "$release_dir" "$previous"; then
      echo "Automatic recovery failed" >&2
    fi
    return 1
  fi
  if ! wait_for_internal_health; then
    echo "Release $release_id failed internal health checks" >&2
    if ! restore_previous_or_stop "$deploy_root" "$release_dir" "$previous"; then
      echo "Automatic recovery failed" >&2
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
  set_deployment_mode "$(release_deployment_mode "$previous")"
  compose config -q
  compose up -d --no-build --remove-orphans
  wait_for_internal_health
  activate_release "$deploy_root" "$previous"
  rm -f "$previous_file"
  echo "Rolled back to $(basename "$previous")"
}

abort_release() {
  local deploy_root=$1
  if [[ -f "$deploy_root/.previous-release" ]]; then
    rollback "$deploy_root"
    return
  fi

  local current_link="$deploy_root/current"
  [[ -L "$current_link" ]] || {
    echo "No active release exists to abort" >&2
    return 1
  }
  local current
  current=$(readlink -f "$current_link")
  [[ -d "$current" && -f "$current/.env" ]] || {
    echo "Active release is unavailable: $current" >&2
    return 1
  }

  cd "$current"
  set_deployment_mode "$(release_deployment_mode "$current")"
  compose down --remove-orphans
  rm -f "$current_link"
  echo "Stopped failed initial release $(basename "$current")"
}

case ${1:-} in
  deploy)
    [[ $# -eq 3 || $# -eq 4 ]] || usage
    deploy "$2" "$3" "${4:-public}"
    ;;
  rollback)
    [[ $# -eq 2 ]] || usage
    rollback "$2"
    ;;
  abort)
    [[ $# -eq 2 ]] || usage
    abort_release "$2"
    ;;
  *) usage ;;
esac

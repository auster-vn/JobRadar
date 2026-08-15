#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Usage: $0 <deploy-root> [releases-to-retain]" >&2
  exit 2
}

[[ $# -ge 1 && $# -le 2 ]] || usage

deploy_root=$1
retain_count=${2:-5}
[[ "$deploy_root" == /* && "$deploy_root" != "/" ]] || usage
[[ "$retain_count" =~ ^[1-9][0-9]*$ ]] || usage
[[ -d "$deploy_root" ]] || usage

deploy_root=$(readlink -f -- "$deploy_root")
[[ "$deploy_root" != "/" ]] || usage
releases_root="$deploy_root/releases"
[[ -d "$releases_root" ]] || exit 0
[[ ! -L "$releases_root" ]] || {
  echo "Refusing to prune a symlinked releases directory: $releases_root" >&2
  exit 1
}

declare -A retained_releases=()
declare -A retained_images=()
declare -A managed_repositories=()

retain_release() {
  local candidate=$1
  local resolved

  resolved=$(readlink -f -- "$candidate") || return 0
  [[ -d "$resolved" && "$resolved" == "$releases_root/"* ]] || return 0
  retained_releases["$resolved"]=1
}

mapfile -d '' -t release_entries < <(
  find "$releases_root" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\0' \
    | sort -z -nr
)

release_dirs=()
for entry in "${release_entries[@]}"; do
  release_dir=${entry#* }
  [[ ${release_dir##*/} =~ ^[A-Za-z0-9._-]+$ ]] || {
    echo "Refusing to prune an invalid release path: $release_dir" >&2
    exit 1
  }
  release_dirs+=("$release_dir")
done

for ((index = 0; index < ${#release_dirs[@]} && index < retain_count; index++)); do
  retain_release "${release_dirs[$index]}"
done

if [[ -L "$deploy_root/current" ]]; then
  retain_release "$deploy_root/current"
fi
if [[ -f "$deploy_root/.previous-release" ]]; then
  IFS= read -r previous_release < "$deploy_root/.previous-release" || true
  [[ -n ${previous_release:-} ]] && retain_release "$previous_release"
fi

for release_dir in "${!retained_releases[@]}"; do
  env_file="$release_dir/.env"
  [[ -f "$env_file" ]] || {
    echo "Retained release is missing .env: $release_dir" >&2
    exit 1
  }

  declare -A seen_image_keys=()
  image_count=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    case $line in
      BACKEND_IMAGE=* | ML_IMAGE=* | WEB_IMAGE=*)
        key=${line%%=*}
        image=${line#*=}
        case $key in
          BACKEND_IMAGE) component=backend ;;
          ML_IMAGE) component=ml ;;
          WEB_IMAGE) component=web ;;
          *) exit 1 ;;
        esac
        [[ -z ${seen_image_keys["$key"]+present} ]] || {
          echo "Duplicate $key in $env_file" >&2
          exit 1
        }
        [[ "$image" =~ ^ghcr\.io/[a-z0-9._-]+/jobradarvn-${component}:[0-9a-f]{40}$ ]] || {
          echo "Unsafe production image reference in $env_file: $image" >&2
          exit 1
        }
        seen_image_keys["$key"]=1
        retained_images["$image"]=1
        managed_repositories["${image%:*}"]=1
        ((image_count += 1))
        ;;
    esac
  done < "$env_file"

  ((image_count == 3)) || {
    echo "Expected three immutable image references in $env_file" >&2
    exit 1
  }
done

for release_dir in "${release_dirs[@]}"; do
  if [[ -z ${retained_releases["$release_dir"]+present} ]]; then
    rm -rf -- "$release_dir"
  fi
done

declare -A container_images=()
container_image_inventory=$(docker container ls --all --format '{{.Image}}')
while IFS= read -r image; do
  [[ -n "$image" ]] && container_images["$image"]=1
done <<< "$container_image_inventory"

image_inventory=$(docker image ls --format '{{.Repository}}:{{.Tag}}')
while IFS= read -r image; do
  case $image in
    ghcr.io/*/jobradarvn-backend:* | ghcr.io/*/jobradarvn-ml:* | ghcr.io/*/jobradarvn-web:*)
      repository=${image%:*}
      if [[ -n ${managed_repositories["$repository"]+present} \
        && -z ${retained_images["$image"]+present} \
        && -z ${container_images["$image"]+present} ]]; then
        if ! docker image rm "$image"; then
          echo "Keeping image still referenced by a container: $image" >&2
        fi
      fi
      ;;
  esac
done <<< "$image_inventory"

docker image prune -f >/dev/null
echo "Retained ${#retained_releases[@]} production releases"

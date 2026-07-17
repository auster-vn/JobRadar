#!/usr/bin/env bash
set -Eeuo pipefail

base_url=${1:?Usage: production_smoke.sh https://jobradar.example}
base_url=${base_url%/}

curl_args=(
  --fail
  --silent
  --show-error
  --location
  --retry 8
  --retry-all-errors
  --retry-delay 3
  --connect-timeout 5
  --max-time 20
)

if [[ "$base_url" == https://* ]]; then
  curl_args+=(--proto '=https' --tlsv1.2)
fi

health=$(curl "${curl_args[@]}" "$base_url/health/ready")
[[ "$health" == *'"status":"ready"'* ]] || {
  echo "Unexpected readiness response: $health" >&2
  exit 1
}

curl "${curl_args[@]}" "$base_url/" >/dev/null
curl "${curl_args[@]}" "$base_url/api/jobs?limit=1" >/dev/null
curl "${curl_args[@]}" "$base_url/api/salary/bands" >/dev/null

echo "Production smoke test passed for $base_url"

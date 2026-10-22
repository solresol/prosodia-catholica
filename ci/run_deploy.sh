#!/usr/bin/env bash
# Host-local settings select the existing approved checkout and execution user.
# Their values and production diagnostics are never emitted to CI logs.
set -euo pipefail
expected=${1:?expected source commit required}
mode=${2:-publish}
[[ "$expected" =~ ^[0-9a-f]{40}$ ]] || exit 2
case "$mode" in daily|publish) ;; *) exit 2;; esac
root=${HERODIAN_DEPLOY_ROOT:-}
account=${HERODIAN_DEPLOY_USER:-}
if [[ -z "$root" || -z "$account" || $(id -un) != "$account" || ! -d "$root/.git" ]]; then
  echo 'Approved local deployment configuration is required' >&2
  exit 77
fi
cd "$root" 2>/dev/null || exit 77
mkdir -p logs 2>/dev/null || exit 77
exec 9>logs/pipeline.lock
log=$(mktemp logs/ci-run.XXXXXXXX.log)
exec 8>&1
unchanged=0
finish() {
  status=$?
  trap - EXIT
  if (( status )); then
    echo "Deployment failed (exit $status); inspect private local diagnostics" >&8
  else
    rm -f "$log"
    if (( unchanged )); then
      echo "No changes since verified publication of $expected" >&8
    else
      echo "Publication verified: source=$expected manifest_sha256=$local_hash" >&8
    fi
  fi
  exit "$status"
}
trap finish EXIT
deploy() {
  flock -w 300 9
  [[ $(git remote get-url origin) == git@github.com:solresol/prosodia-catholica.git ]]
  [[ $(git branch --show-current) == main && -z $(git status --porcelain) ]]
  git fetch --quiet origin main
  git merge-base --is-ancestor "$expected" origin/main
  git merge --ff-only "$expected"
  [[ $(git rev-parse HEAD) == "$expected" ]]
  [[ $(python3 -c 'import config; print(config.GADGET_WORKFLOW)') == cloud ]]
  day=$(TZ=Australia/Sydney date +%Y%m%d)
  data_ref=$(git ls-remote origin refs/heads/gadget-handoff | cut -f1)
  key="$expected $day $data_ref"
  if [[ -f logs/ci-published && $(cat logs/ci-published) == "$key" ]] && { [[ "$mode" == publish ]] || [[ -f "logs/daily-${day}.done" ]]; }; then
    unchanged=1
    return 0
  fi
  HERODIAN_LOCK_INHERITED=1 HERODIAN_EXPECTED_SHA="$expected" ./run_daily_pipeline.sh "$mode"
  local_hash=$(sha256sum site/ci-deployment.json | cut -d' ' -f1)
  target=$(python3 -c 'import config; print(config.DEPLOY_HOST)')
  destination=$(python3 -c 'import config; print(config.DEPLOY_PATH)')
  # Restrict characters before passing configured paths through remote shell.
  [[ "$target" =~ ^[a-zA-Z0-9_.-]+$ && "$destination" =~ ^/[a-zA-Z0-9_./-]+$ ]]
  remote_hash=$(ssh -o BatchMode=yes "$target" sha256 -q "$destination/ci-deployment.json")
  [[ "$local_hash" == "$remote_hash" ]]
  data_ref=$(git ls-remote origin refs/heads/gadget-handoff | cut -f1)
  printf '%s\n' "$expected $day $data_ref" > logs/ci-published.tmp
  mv logs/ci-published.tmp logs/ci-published
}
deploy >"$log" 2>&1

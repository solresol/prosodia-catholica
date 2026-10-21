#!/usr/bin/env bash
# Staged replacement for cron. Does not generate content or change the schema.
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"
cd "$(dirname "$0")"
mkdir -p logs
exec 9>logs/site-publish.lock
if ! flock -n 9; then
  echo 'Site publish already running' >&2
  exit 75
fi
log=$(mktemp logs/site-publish.XXXXXXXX.log)
finish() {
  status=$?
  trap - EXIT
  if (( status != 0 )); then
    echo "Site publish failed (exit $status); log: $PWD/$log" >&2
    cat "$log" >&2
  else
    rm -f "$log"
  fi
  exit "$status"
}
trap finish EXIT
publish() {
  # Refuse stale/dirty deployments; do not swallow pull failures.
  test -z "$(git status --porcelain)" || { echo 'Checkout must be clean'; return 1; }
  test "$(git remote get-url origin)" = 'git@github.com:solresol/prosodia-catholica.git' || return 1
  git pull --ff-only
  uv run --frozen generate_site.py --overlap-metric-version "${OVERLAP_METRIC_VERSION:-v1}"
  DEPLOY_HOST=$(python3 -c 'import config; print(config.DEPLOY_HOST)')
  DEPLOY_PATH=$(python3 -c 'import config; print(config.DEPLOY_PATH)')
  test "$DEPLOY_HOST" = merah
  test "$DEPLOY_PATH" = /var/www/vhosts/prosodia-catholica.symmachus.org/htdocs
  test -s site/index.html
  rsync -az --delete site/ "${DEPLOY_HOST}:${DEPLOY_PATH}/"
  # Only a successful deployment advances the public-data handoff baseline.
  snapshot=$(mktemp logs/published-passages.XXXXXXXX.json)
  cp site/passages.json "$snapshot"
  mv -f "$snapshot" logs/published-passages.json
}
publish >"$log" 2>&1

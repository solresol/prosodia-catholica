#!/usr/bin/env bash
# Staged replacement. Do not select alongside the DB-backed cron.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs
exec 9>logs/pipeline.lock
flock -n 9 || exit 0
runlog=$(mktemp logs/git-run.XXXXXXXX.log)
finish() {
 status=$?
 trap - EXIT
 if (( status )); then cat "$runlog" >&2; else rm -f "$runlog"; fi
 exit "$status"
}
trap finish EXIT
pipeline() {
 test "$(git branch --show-current)" = main
 test -z "$(git status --porcelain --untracked-files=no)"
 git pull --ff-only origin main
 # No schema initialization, private TSV import, or legacy gadget API generation.
 uv run generate_content.py translation --limit "${TRANSLATION_LIMIT:-5}" --delay "${TRANSLATION_DELAY:-1}"
 uv run generate_content.py summary --limit "${SUMMARY_LIMIT:-25}" --delay "${SUMMARY_DELAY:-0.5}"
 python3 - <<'PYCODE'
from git_content_workflow import publish_content
from content_store import DEFAULT, workflow_lock
with workflow_lock():
    publish_content(DEFAULT)
PYCODE
 uv run git_content_workflow.py import-ready
 python3 tests/offline_build.py --out site
 # Existing host-local configuration and transport; never emitted to hosted CI.
 deploy_host=$(python3 -c 'import config; print(config.DEPLOY_HOST)')
 deploy_path=$(python3 -c 'import config; print(config.DEPLOY_PATH)')
 rsync -az --delete site/ "$deploy_host:$deploy_path/"
 uv run git_content_workflow.py enqueue --published-file site/passages.json
}
pipeline >"$runlog" 2>&1

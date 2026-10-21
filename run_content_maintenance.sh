#!/usr/bin/env bash
# Staged local maintenance: preserve non-gadget daily progress on Raksasa.
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"
cd "$(dirname "$0")"
mkdir -p logs
exec 9>logs/content-maintenance.lock
if ! flock -n 9; then
  echo 'Content maintenance already running' >&2
  exit 75
fi
log=$(mktemp logs/content-maintenance.XXXXXXXX.log)
finish() {
  status=$?
  trap - EXIT
  if (( status != 0 )); then
    echo "Content maintenance failed (exit $status); log: $PWD/$log" >&2
    cat "$log" >&2
  else
    rm -f "$log"
  fi
  exit "$status"
}
trap finish EXIT
maintain() {
  export TRANSLATION_LIMIT="${TRANSLATION_LIMIT:-5}"
  export TRANSLATION_DELAY="${TRANSLATION_DELAY:-1}"
  export SUMMARY_LIMIT="${SUMMARY_LIMIT:-25}"
  export SUMMARY_DELAY="${SUMMARY_DELAY:-0.5}"
  export PIPELINE_RUNS_PER_DAY="${PIPELINE_RUNS_PER_DAY:-1}"
  export OVERLAP_METRIC_VERSION="${OVERLAP_METRIC_VERSION:-v1}"
  export OVERLAP_MAX_MATCHES="${OVERLAP_MAX_MATCHES:-10}"
  uv run --frozen translate_lines.py --limit "$TRANSLATION_LIMIT" --delay "$TRANSLATION_DELAY"
  uv run --frozen summarize_lines.py --limit "$SUMMARY_LIMIT" --delay "$SUMMARY_DELAY"
  uv run --frozen compute_overlaps.py --metric-version "$OVERLAP_METRIC_VERSION" --max-matches "$OVERLAP_MAX_MATCHES"
}
maintain >"$log" 2>&1

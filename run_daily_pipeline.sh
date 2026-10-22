#!/usr/bin/env bash
set -euo pipefail

export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"

cd "$(dirname "$0")"

mkdir -p logs
MODE="${1:-daily}"
case "$MODE" in daily|publish) ;; *) echo 'Expected daily or publish' >&2; exit 2;; esac
# Same inode for cron and CI in the existing production checkout.
if [[ "${HERODIAN_LOCK_INHERITED:-}" != 1 ]] || [[ ! /proc/self/fd/9 -ef logs/pipeline.lock ]]; then
  exec 9>logs/pipeline.lock
fi
if ! flock -n 9; then
  echo 'Herodian pipeline already running' >&2
  exit 75
fi

LOGFILE="pipeline.log"
DATE="$(TZ=Australia/Sydney date +%Y%m%d)"
DAILY_WORK=0
if [[ "$MODE" == daily ]]; then
  if [[ -f "logs/daily-${DATE}.done" ]]; then
    MODE=publish
  elif [[ -f "logs/daily-${DATE}.started" ]]; then
    echo 'Daily source work has an incomplete receipt; inspect before retrying' >&2
    exit 75
  else
    DAILY_WORK=1
  fi
fi

pipeline() {
echo "========================================" | tee -a "$LOGFILE"
echo "Prosodia Catholica pipeline: $(date)" | tee -a "$LOGFILE"
echo "========================================" | tee -a "$LOGFILE"

echo "Step 0: git pull (if clean)..." | tee -a "$LOGFILE"
if [[ -n "${HERODIAN_EXPECTED_SHA:-}" ]]; then
  test "$(git rev-parse HEAD)" = "$HERODIAN_EXPECTED_SHA"
elif git diff --quiet && git diff --cached --quiet; then
  git pull 2>&1 | tee -a "$LOGFILE" || echo "Git pull failed (continuing)" | tee -a "$LOGFILE"
else
  echo "Git working tree has local changes; skipping git pull" | tee -a "$LOGFILE"
fi

if (( DAILY_WORK )); then
  date --iso-8601=seconds > "logs/daily-${DATE}.started"
echo "Step 1: init DB schema..." | tee -a "$LOGFILE"
uv run init_db.py 2>&1 | tee -a "$LOGFILE"

TRANSLATION_LIMIT="${TRANSLATION_LIMIT:-5}"
TRANSLATION_DELAY="${TRANSLATION_DELAY:-1}"
PIPELINE_RUNS_PER_DAY="${PIPELINE_RUNS_PER_DAY:-1}"
export TRANSLATION_LIMIT TRANSLATION_DELAY PIPELINE_RUNS_PER_DAY

echo "Step 2: translate up to ${TRANSLATION_LIMIT} lines..." | tee -a "$LOGFILE"
uv run translate_lines.py --limit "$TRANSLATION_LIMIT" --delay "$TRANSLATION_DELAY" 2>&1 | tee -a "$LOGFILE"

SUMMARY_LIMIT="${SUMMARY_LIMIT:-25}"
SUMMARY_DELAY="${SUMMARY_DELAY:-0.5}"
export SUMMARY_LIMIT SUMMARY_DELAY

echo "Step 2b: summarize up to ${SUMMARY_LIMIT} lines..." | tee -a "$LOGFILE"
uv run summarize_lines.py --limit "$SUMMARY_LIMIT" --delay "$SUMMARY_DELAY" 2>&1 | tee -a "$LOGFILE"

fi

GADGET_STATUS=0
GADGET_WORKFLOW="${GADGET_WORKFLOW:-$(python3 -c 'import config; print(getattr(config, "GADGET_WORKFLOW", "legacy"))')}"
case "$GADGET_WORKFLOW" in
  legacy)
    if (( DAILY_WORK )); then
    GADGET_LIMIT="${GADGET_LIMIT:-1}"
    GADGET_DELAY="${GADGET_DELAY:-0}"
    export GADGET_LIMIT GADGET_DELAY
    echo "Step 2bb: generate up to ${GADGET_LIMIT} gadgets..." | tee -a "$LOGFILE"
    uv run gadgetize_lines.py --limit "$GADGET_LIMIT" --delay "$GADGET_DELAY" 2>&1 | tee -a "$LOGFILE"
    fi
    ;;
  cloud)
    echo "Step 2bb: import any tested cloud gadget result..." | tee -a "$LOGFILE"
    uv run git_gadget_handoff.py import-ready 2>&1 | tee -a "$LOGFILE" || GADGET_STATUS=$?
    ;;
  *) echo "Unknown GADGET_WORKFLOW: $GADGET_WORKFLOW" >&2; return 2 ;;
esac

OVERLAP_METRIC_VERSION="${OVERLAP_METRIC_VERSION:-v1}"
OVERLAP_MAX_MATCHES="${OVERLAP_MAX_MATCHES:-10}"
export OVERLAP_METRIC_VERSION OVERLAP_MAX_MATCHES

if (( DAILY_WORK )); then
echo "Step 3: compute Stephanos overlaps (${OVERLAP_METRIC_VERSION})..." | tee -a "$LOGFILE"
uv run compute_overlaps.py --metric-version "$OVERLAP_METRIC_VERSION" --max-matches "$OVERLAP_MAX_MATCHES" 2>&1 | tee -a "$LOGFILE"
date --iso-8601=seconds > "logs/daily-${DATE}.done"
fi

echo "Step 4: generate site..." | tee -a "$LOGFILE"
uv run generate_site.py --overlap-metric-version "$OVERLAP_METRIC_VERSION" 2>&1 | tee -a "$LOGFILE"

echo "Step 5: deploy site via rsync..." | tee -a "$LOGFILE"
DEPLOY_HOST="$(python3 -c 'import config; print(getattr(config, "DEPLOY_HOST", "merah"))')"
DEPLOY_PATH="$(python3 -c 'import config; print(getattr(config, "DEPLOY_PATH", "/var/www/vhosts/prosodia-catholica.symmachus.org/htdocs"))')"

if [[ -n "${HERODIAN_EXPECTED_SHA:-}" ]]; then
  [[ "$HERODIAN_EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]
  printf '{"source_commit":"%s"}\n' "$HERODIAN_EXPECTED_SHA" > site/ci-deployment.json
fi
rsync -az --delete site/ "${DEPLOY_HOST}:${DEPLOY_PATH}/" 2>&1 | tee -a "$LOGFILE"

if [[ "$GADGET_WORKFLOW" == cloud ]]; then
  # rsync succeeded: this exact snapshot is now public. Queue only these fields.
  echo "Queue next cloud gadget assignment..." | tee -a "$LOGFILE"
  uv run git_gadget_handoff.py enqueue --published-file site/passages.json 2>&1 | tee -a "$LOGFILE" || GADGET_STATUS=$?
fi

echo "Pipeline complete: $(date)" | tee -a "$LOGFILE"
echo "" | tee -a "$LOGFILE"

cp -f "$LOGFILE" "logs/pipeline_${DATE}.log" || true
return "$GADGET_STATUS"

}

# Keep useful per-run failure output without cron mail on success.
RUNLOG=$(mktemp logs/cron-run.XXXXXXXX.log)
exec 8>&2
finish() {
  status=$?
  trap - EXIT
  if (( status != 0 )); then
    echo "Herodian pipeline failed (exit $status); log: $PWD/$RUNLOG" >&8
    cat "$RUNLOG" >&8
  else
    rm -f "$RUNLOG"
  fi
  exit "$status"
}
trap finish EXIT
pipeline >"$RUNLOG" 2>&1

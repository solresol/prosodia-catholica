#!/usr/bin/env bash
set -euo pipefail

export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"

cd "$(dirname "$0")"

mkdir -p logs

LOGFILE="pipeline.log"
DATE="$(date +%Y%m%d)"

pipeline() {
echo "========================================" | tee -a "$LOGFILE"
echo "Prosodia Catholica pipeline: $(date)" | tee -a "$LOGFILE"
echo "========================================" | tee -a "$LOGFILE"

echo "Step 0: git pull (if clean)..." | tee -a "$LOGFILE"
if git diff --quiet && git diff --cached --quiet; then
  git pull 2>&1 | tee -a "$LOGFILE" || echo "Git pull failed (continuing)" | tee -a "$LOGFILE"
else
  echo "Git working tree has local changes; skipping git pull" | tee -a "$LOGFILE"
fi

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

GADGET_STATUS=0
GADGET_WORKFLOW="${GADGET_WORKFLOW:-$(python3 -c 'import config; print(getattr(config, "GADGET_WORKFLOW", "legacy"))')}"
case "$GADGET_WORKFLOW" in
  legacy)
    GADGET_LIMIT="${GADGET_LIMIT:-1}"
    GADGET_DELAY="${GADGET_DELAY:-0}"
    export GADGET_LIMIT GADGET_DELAY
    echo "Step 2bb: generate up to ${GADGET_LIMIT} gadgets..." | tee -a "$LOGFILE"
    uv run gadgetize_lines.py --limit "$GADGET_LIMIT" --delay "$GADGET_DELAY" 2>&1 | tee -a "$LOGFILE"
    ;;
  cloud)
    echo "Step 2bb: import any tested cloud gadget result..." | tee -a "$LOGFILE"
    uv run git_gadget_handoff.py import-ready 2>&1 | tee -a "$LOGFILE" || GADGET_STATUS=$?
    ;;
  *) echo "Unknown GADGET_WORKFLOW: $GADGET_WORKFLOW" >&2; return 2 ;;
esac

echo "Step 4: generate site..." | tee -a "$LOGFILE"
uv run generate_site.py 2>&1 | tee -a "$LOGFILE"

echo "Step 5: deploy site via rsync..." | tee -a "$LOGFILE"
DEPLOY_HOST="$(python3 -c 'import config; print(getattr(config, "DEPLOY_HOST", "merah"))')"
DEPLOY_PATH="$(python3 -c 'import config; print(getattr(config, "DEPLOY_PATH", "/var/www/vhosts/prosodia-catholica.symmachus.org/htdocs"))')"

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

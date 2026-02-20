#!/usr/bin/env bash
set -euo pipefail

export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"

cd "$(dirname "$0")"

mkdir -p logs

LOGFILE="pipeline.log"
DATE="$(date +%Y%m%d)"

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

echo "Step 2: import TSV (if present)..." | tee -a "$LOGFILE"
if [ -f "HerodianCathPros.txt" ]; then
  uv run import_herodian_tsv.py HerodianCathPros.txt 2>&1 | tee -a "$LOGFILE"
else
  echo "No HerodianCathPros.txt present; skipping import" | tee -a "$LOGFILE"
fi

TRANSLATION_LIMIT="${TRANSLATION_LIMIT:-5}"
TRANSLATION_DELAY="${TRANSLATION_DELAY:-1}"

echo "Step 3: translate up to ${TRANSLATION_LIMIT} lines..." | tee -a "$LOGFILE"
uv run translate_lines.py --limit "$TRANSLATION_LIMIT" --delay "$TRANSLATION_DELAY" 2>&1 | tee -a "$LOGFILE"

SUMMARY_LIMIT="${SUMMARY_LIMIT:-25}"
SUMMARY_DELAY="${SUMMARY_DELAY:-0.5}"

echo "Step 3b: summarize up to ${SUMMARY_LIMIT} lines..." | tee -a "$LOGFILE"
uv run summarize_lines.py --limit "$SUMMARY_LIMIT" --delay "$SUMMARY_DELAY" 2>&1 | tee -a "$LOGFILE"

OVERLAP_METRIC_VERSION="${OVERLAP_METRIC_VERSION:-v1}"
OVERLAP_MAX_MATCHES="${OVERLAP_MAX_MATCHES:-10}"

echo "Step 3c: compute Stephanos overlaps (${OVERLAP_METRIC_VERSION})..." | tee -a "$LOGFILE"
uv run compute_overlaps.py --metric-version "$OVERLAP_METRIC_VERSION" --max-matches "$OVERLAP_MAX_MATCHES" 2>&1 | tee -a "$LOGFILE"

echo "Step 4: generate site..." | tee -a "$LOGFILE"
uv run generate_site.py 2>&1 | tee -a "$LOGFILE"

echo "Step 5: deploy site via rsync..." | tee -a "$LOGFILE"
DEPLOY_HOST="$(python3 -c 'import config; print(getattr(config, "DEPLOY_HOST", "merah"))')"
DEPLOY_PATH="$(python3 -c 'import config; print(getattr(config, "DEPLOY_PATH", "/var/www/vhosts/prosodia-catholica.symmachus.org/htdocs"))')"

rsync -az --delete site/ "${DEPLOY_HOST}:${DEPLOY_PATH}/" 2>&1 | tee -a "$LOGFILE"

echo "Pipeline complete: $(date)" | tee -a "$LOGFILE"
echo "" | tee -a "$LOGFILE"

cp -f "$LOGFILE" "logs/pipeline_${DATE}.log" || true

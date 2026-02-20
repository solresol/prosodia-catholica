#!/usr/bin/env bash
set -euo pipefail

CRON_FILE="/tmp/prosodia_catholica_cron.txt"

cat > "$CRON_FILE" <<'EOF'
# Prosodia Catholica (Herodian) - Daily pipeline
# Runs at 1:15 AM daily (server local time)
15 1 * * * cd ~/prosodia-catholica && ./run_daily_pipeline.sh >> logs/cron.log 2>&1
EOF

mkdir -p "$HOME/prosodia-catholica/logs"

crontab -l > /tmp/current_cron.txt 2>/dev/null || touch /tmp/current_cron.txt

if grep -q "Prosodia Catholica (Herodian) - Daily pipeline" /tmp/current_cron.txt; then
  echo "Cron entry already present; nothing to do."
  exit 0
fi

cat /tmp/current_cron.txt "$CRON_FILE" | crontab -

echo "OK: installed cron job."
crontab -l | grep -n "Prosodia Catholica (Herodian)" || true

rm -f "$CRON_FILE" /tmp/current_cron.txt

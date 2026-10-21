#!/usr/bin/env bash
# Staged local queue/import wrapper. Never called by the active legacy cron.
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"
cd "$(dirname "$0")"
mkdir -p logs
exec 9>logs/gadget-handoff.lock
if ! flock -n 9; then
  echo 'Local gadget handoff already running' >&2
  exit 75
fi
case "${1:-}" in enqueue|import) ;; *) echo 'Expected enqueue or import' >&2; exit 2;; esac
log=$(mktemp logs/gadget-handoff.XXXXXXXX.log)
finish() {
  status=$?
  trap - EXIT
  if (( status != 0 )); then
    echo "Gadget handoff failed (exit $status); log: $PWD/$log" >&2
    cat "$log" >&2
  else
    rm -f "$log"
  fi
  exit "$status"
}
trap finish EXIT
if [[ "$1" == enqueue ]]; then
  uv run --frozen git_gadget_handoff.py enqueue --published-file logs/published-passages.json >"$log" 2>&1
else
  uv run --frozen git_gadget_handoff.py import >"$log" 2>&1
fi

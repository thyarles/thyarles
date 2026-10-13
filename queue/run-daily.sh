#!/bin/bash
# Called hourly by launchd while the Mac is awake; fetches at most once per day.
# A failed fetch leaves no stamp, so the next hour tries again.
set -uo pipefail

STATE="${QUEUE_STATE:-$HOME/.queue-tracker}"
STAMP="$STATE/last-run"
TODAY="$(date +%F)"
export GIT_TERMINAL_PROMPT=0

cd "$(dirname "$0")/.." || exit 1
[[ -f "$STAMP" && "$(cat "$STAMP")" == "$TODAY" ]] && exit 0

echo "== $(date '+%F %T')"
git pull --rebase --quiet || exit 1
python3 queue/track.py
status=$?

git add queue/data queue/README.md
if ! git diff --cached --quiet; then
  git commit --quiet -m "chore(queue): add reading of $TODAY" && git push --quiet || exit 1
fi
[[ $status -eq 0 ]] && echo "$TODAY" > "$STAMP"
exit $status

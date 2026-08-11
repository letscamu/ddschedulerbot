#!/bin/bash
# DynaBot Feedback Pipeline — Auto Issue Creator
# Runs on schedule via launchd on mothership
# Hours 6-12 Central Time (configured in plist)
#
# THE FAILURE PATH IS THE POINT. This script used to have no `set -e`: when the
# interpreter on line 16 vanished it printed "Done." and exited 0, so launchd
# recorded success and nothing alerted. It failed that way 49 consecutive times
# between 2026-08-04 06:00 and 2026-08-10 12:00 — six days of green signals over
# a dead job, the same equivalence class as the Aug 4-6 incident that Boothby was
# built to prevent. Any non-fatal error path added below rebuilds that bug.
#
# Root cause of that outage: `.venv-pipeline` was built against Homebrew
# python@3.13, and a brew upgrade to python@3.14 deleted the Cellar path its
# symlinks pointed at. This now uses the repo's main `.venv` (pyenv 3.12.3),
# which already carries google-cloud-storage and the backend package, so there
# is one fewer venv to keep alive.

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HOME="/Users/seanfilipow"
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/gcloud/feedback-pipeline-sa-key.json"

REPO="/Users/seanfilipow/CAMU/ddschedulerbot"
LOG_DIR="$REPO/logs"
PYTHON="$REPO/.venv/bin/python3"
NTFY_TOPIC="sfil_ccalt_0326"
mkdir -p "$LOG_DIR"

ntfy() {  # ntfy <title> <priority> <body>
  curl -s -H "Title: $1" -H "Priority: $2" -d "$3" \
    "https://ntfy.sh/$NTFY_TOPIC" > /dev/null || \
    echo "[$(date)] warn: ntfy push failed (offline?)"
}

fail_loudly() {
  rc=$?
  echo "[$(date)] FAILED (exit $rc) at stage '${STAGE:-unknown}'"
  ntfy "⚠️ DynaBot feedback pipeline FAILED" "high" \
    "Exit $rc at stage '${STAGE:-unknown}' on Mothership. No issues created this run. See logs/feedback-pipeline.log."
  exit "$rc"
}
trap fail_loudly ERR

STAGE="preflight"
# Check the interpreter and the credential explicitly. A missing venv is the
# failure that caused the six-day outage, so it gets a named error rather than
# a bare "No such file or directory" buried in a log nobody reads.
[[ -x "$PYTHON" ]] || {
  echo "[$(date)] interpreter missing or not executable: $PYTHON"
  ntfy "⚠️ DynaBot pipeline: venv broken" "high" \
    "$PYTHON is missing or not executable on Mothership — likely a brew/pyenv Python upgrade. Rebuild the venv."
  exit 1
}
[[ -r "$GOOGLE_APPLICATION_CREDENTIALS" ]] || {
  echo "[$(date)] service account key unreadable: $GOOGLE_APPLICATION_CREDENTIALS"
  ntfy "⚠️ DynaBot pipeline: SA key missing" "high" \
    "Service account key unreadable on Mothership. Pipeline cannot reach GCS."
  exit 1
}

echo "[$(date)] Starting feedback pipeline run..."
cd "$REPO"

STAGE="create-issues"
"$PYTHON" tools/feedback_pipeline.py --prod create-issues --yes

STAGE="done"
echo "[$(date)] Done."

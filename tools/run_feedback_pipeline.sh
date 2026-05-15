#!/bin/bash
# DynaBot Feedback Pipeline — Auto Issue Creator
# Runs on schedule via launchd on mothership
# Hours 6-12 Central Time (configured in plist)

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HOME="/Users/seanfilipow"
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/gcloud/feedback-pipeline-sa-key.json"

REPO="/Users/seanfilipow/CAMU/ddschedulerbot"
LOG_DIR="$REPO/logs"
mkdir -p "$LOG_DIR"

echo "[$(date)] Starting feedback pipeline run..."
cd "$REPO"
"$REPO/.venv-pipeline/bin/python3" tools/feedback_pipeline.py --prod create-issues --yes
echo "[$(date)] Done."

# Copy this file to config.sh (same folder) and fill in the values.

# GitHub repo that the dashboard image is published to (owner/name).
REPO="OWNER/kindle-dashboard"
# Branch the GitHub Action publishes dashboard.png to.
BRANCH="output"
# Fine-grained personal access token for this repo only: "Contents: Read-only" and
# "Actions: Read and write" (so the Kindle can ask GitHub for a fresh render).
GITHUB_TOKEN=""
# Refresh at this minute past every hour (the Action renders at :45).
REFRESH_MINUTE=5
# Night sleep (local time): the dashboard sleeps from NIGHT_START:00 to NIGHT_END:00.
NIGHT_START=0
NIGHT_END=6
# 1: try a real deep sleep at night (best for battery); 0: just idle with Wi-Fi off.
NIGHT_SUSPEND=1

# Copy this file to config.sh (same folder) and fill in the values.

# GitHub repo that the dashboard image is published to (owner/name).
REPO="OWNER/kindle-dashboard"
# Branch the GitHub Action publishes dashboard.png to.
BRANCH="output"
# Fine-grained personal access token: this repo only, "Contents: Read-only".
GITHUB_TOKEN=""
# Refresh at this minute past every hour (the Action renders at :45).
REFRESH_MINUTE=5

# Copy this file to config.sh (same folder) and fill in the values. config.sh stays on the Kindle:
# updates never overwrite it. Everything else is in settings.sh, which comes from GitHub.

# GitHub repo that the dashboard image is published to (owner/name).
REPO="OWNER/kindle-dashboard"
# Fine-grained personal access token for this repo only: "Contents: Read-only" and
# "Actions: Read and write" (so the Kindle can ask GitHub for a fresh render and send its log).
GITHUB_TOKEN=""
# A line such as NIGHT_SUSPEND=1 here overrides settings.sh on this Kindle only.

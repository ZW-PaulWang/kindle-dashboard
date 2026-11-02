# Dashboard settings. This file is part of the repo (kindle/dashboard/settings.sh) and reaches the
# Kindle with every over-the-air update, so change it on GitHub, not on the Kindle.
# config.sh on the Kindle is read after this file, so a setting there still wins.

# Branch the GitHub Action publishes the images to.
BRANCH=output
# Refresh at this minute past every hour.
REFRESH_MINUTE=5
# Night sleep (local time): the dashboard sleeps from NIGHT_START:00 to NIGHT_END:00.
NIGHT_START=0
NIGHT_END=6
# 0: idle with Wi-Fi off at night (deep sleep saved no battery and may have caused a crash).
# 1: also try a real deep sleep.
NIGHT_SUSPEND=0
# Bus times: refresh every COMMUTE_EVERY minutes from COMMUTE_START to COMMUTE_END on
# Monday..COMMUTE_LAST_DAY (5 = weekdays, 7 = every day).
COMMUTE_START=7
COMMUTE_END=10
COMMUTE_EVERY=10
COMMUTE_LAST_DAY=5
# 1: install new versions of these scripts from GitHub at each refresh (bin/update.sh).
UPDATES=1
# 1: send new dashboard.log lines to the repo's logs branch with each render request.
LOG_UPLOAD=1

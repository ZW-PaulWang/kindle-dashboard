#!/bin/sh
# Launched from KUAL. Detach the dashboard loop so it survives the UI shutting down.
DIR="/mnt/us/extensions/dashboard"
PIDFILE="/tmp/dashboard.pid"   # same as common.sh
LOG="$DIR/dashboard.log"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >>"$LOG"; }

log "Start requested from KUAL"
rm -f "$DIR/dashboard.pid"   # old location; it could outlive a crash and block every start
# Already running? Only trust the pid file if that process really is dash.sh: after a crash or a
# restart the old number can belong to another process, which made this exit without a word.
if [ -f "$PIDFILE" ]; then
    pid="$(cat "$PIDFILE" 2>/dev/null)"
    # cmdline is NUL-separated; busybox grep stops at a NUL, so turn them into spaces first.
    if [ -n "$pid" ] && tr '\0' ' ' 2>/dev/null <"/proc/$pid/cmdline" | grep -qF "bin/dash.sh"; then
        log "Dashboard is already running (pid $pid)"
        exit 0
    fi
    log "Removing stale pid file (pid ${pid:-none} is not the dashboard)"
    rm -f "$PIDFILE"
fi

# Say something right away; the dashboard itself appears once the Kindle UI has stopped.
for fb in /mnt/us/libkh/bin/fbink /mnt/us/koreader/fbink; do
    [ -x "$fb" ] && { "$fb" -q -m -M "Starting dashboard..."; break; }
done

# Install a published update first, so a dashboard broken by a bad version can be fixed from
# GitHub with a tap on Start. A separate shell: a broken common.sh or update.sh can't stop the start.
if ping -c 1 -W 3 api.github.com >/dev/null 2>&1; then
    sh -c '. "$1/bin/common.sh" && . "$1/bin/update.sh" && load_config && apply_update' start "$DIR" >>"$LOG" 2>&1 </dev/null
else
    log "No network; starting without checking for updates"
fi

if command -v setsid >/dev/null 2>&1; then
    setsid sh "$DIR/bin/dash.sh" >>"$LOG" 2>&1 </dev/null &
else
    nohup sh "$DIR/bin/dash.sh" >>"$LOG" 2>&1 </dev/null &
fi
exit 0

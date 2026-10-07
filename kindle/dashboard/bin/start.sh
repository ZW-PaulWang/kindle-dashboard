#!/bin/sh
# Launched from KUAL. Detach the dashboard loop so it survives the UI shutting down.
DIR="/mnt/us/extensions/dashboard"
if [ -f "$DIR/dashboard.pid" ] && kill -0 "$(cat "$DIR/dashboard.pid")" 2>/dev/null; then
    exit 0
fi
if command -v setsid >/dev/null 2>&1; then
    setsid sh "$DIR/bin/dash.sh" >>"$DIR/dashboard.log" 2>&1 </dev/null &
else
    nohup sh "$DIR/bin/dash.sh" >>"$DIR/dashboard.log" 2>&1 </dev/null &
fi
exit 0

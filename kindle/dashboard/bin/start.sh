#!/bin/sh
# Launched from KUAL. Detach the dashboard loop so it survives the UI shutting down.
DIR="/mnt/us/extensions/dashboard"
# Already running? Check that the saved PID is really dash.sh: after a reboot the old PID
# can belong to a system process, and a plain kill -0 would block the start.
pid="$(cat "$DIR/dashboard.pid" 2>/dev/null)"
if [ -n "$pid" ] && tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null | grep -q "dash.sh"; then
    exit 0
fi
rm -f "$DIR/dashboard.pid"
if command -v setsid >/dev/null 2>&1; then
    setsid sh "$DIR/bin/dash.sh" >>"$DIR/dashboard.log" 2>&1 </dev/null &
else
    nohup sh "$DIR/bin/dash.sh" >>"$DIR/dashboard.log" 2>&1 </dev/null &
fi
exit 0

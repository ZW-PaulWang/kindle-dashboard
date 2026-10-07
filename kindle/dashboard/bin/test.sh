#!/bin/sh
# Download the dashboard once without touching the screen; results go to dashboard.log.
. /mnt/us/extensions/dashboard/bin/common.sh
{
    log "Test: starting"
    load_config && fetch_image && log "Test: OK ($IMG)"
    log "fbink: $(find_fbink || echo none); curl: $(command -v curl || echo none)"
} >>"$DIR/dashboard.log" 2>&1

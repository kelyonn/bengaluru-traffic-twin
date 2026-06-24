#!/usr/bin/env bash
# run_24h.sh — full 24-hour mesoscopic pipeline
set -euo pipefail
cd "$(dirname "$0")"

export SUMO_HOME="${SUMO_HOME:-/opt/homebrew/opt/sumo/share/sumo}"
export TOMTOM_API_KEY="${TOMTOM_API_KEY:-}"

caffeinate -i -w $$ &
CAFF=$!
trap "kill $CAFF 2>/dev/null || true" EXIT

log() { echo "[$(date +%H:%M:%S)] $*"; }

log "STEP 1/6: generating 24h demand (~95k trips)…"
python3 generate_demand.py

log "STEP 2/6: duarouter (CH + 8 threads)…"
duarouter \
    -n bengaluru.net.xml \
    -r bengaluru.trips.xml \
    --routing-algorithm CH \
    --routing-threads 8 \
    --ignore-errors \
    --begin 0 --end 86400 \
    -o bengaluru.rou.xml \
    --no-step-log

log "STEP 3/6: SUMO mesoscopic simulation (24h)…"
sumo -c bengaluru.sumocfg \
    --mesosim \
    --device.fcd.period 5 \
    --no-step-log

log "STEP 4/6: build_light_outputs…"
python3 build_light_outputs.py

log "STEP 5/6: simplify_roads…"
python3 simplify_roads.py

log "STEP 6/6: fetch_tomtom + build_analytics…"
if [ -n "$TOMTOM_API_KEY" ]; then
    python3 fetch_tomtom.py
else
    log "  (skipping TomTom — TOMTOM_API_KEY not set, keeping existing tomtom_flow.json)"
fi

python3 build_analytics.py

log "=== ALL DONE ==="

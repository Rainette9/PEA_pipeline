#!/bin/bash
# Daily cron: FTP delta sync + Peddy processing (resume mode) for all sensors.
# PEA_ROOT (default /data/disk1/shared/PEA) selects the data tree; the scripts live next to this file.

PEA_ROOT=${PEA_ROOT:-/data/disk1/shared/PEA}
TS=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LOG=$PEA_ROOT/data/pipeline.log
JULIA_PROJECT=$TS/DataProcessingScriptsJulia
SCRIPTS=$JULIA_PROJECT/scripts
export PEA_ROOT
export PEA_INPUT_BASE=$PEA_ROOT/data
export PEA_HF_OUT=$PEA_ROOT/processed_HF
export PEA_LF_OUT=$PEA_ROOT/processed_LF

echo "=== $(date -u '+%Y-%m-%d %H:%M:%S UTC') Starting daily pipeline ===" >> "$LOG"

# Step 1: Data sync
echo "--- datasync ---" >> "$LOG"
python3 "$TS/datasync-snowflux-pea.py" >> "$LOG" 2>&1
echo "--- datasync done (exit $?) ---" >> "$LOG"

# Step 2: Julia processing (resume mode — skips already-processed dates)
for sensor in SFC LOWER UPPER BOTTOM; do
    echo "--- Processing $sensor ---" >> "$LOG"
    julia --project="$JULIA_PROJECT" "$SCRIPTS/run_${sensor}.jl" >> "$LOG" 2>&1 \
        && echo "--- $sensor done ---" >> "$LOG" \
        || echo "--- $sensor FAILED (exit $?) ---" >> "$LOG"
done

echo "=== $(date -u '+%Y-%m-%d %H:%M:%S UTC') Pipeline complete ===" >> "$LOG"

#!/bin/bash
# Daily cron: FTP delta sync + Peddy processing (resume mode) for all sensors.
# Paths from pea_env.sh (PEA_ROOT, PEA_LOGS, PEA_INPUT_BASE, PEA_HF_OUT, PEA_LF_OUT).
. "$(dirname "${BASH_SOURCE[0]}")/pea_env.sh"
LOG=$PEA_LOGS/pipeline.log
# The run at 02:03 processes yesterday's data; on 1 January that is still last year
# (run_sensor.jl keeps only dates of PEA_YEAR and picks the calibration for it).
export PEA_YEAR=$(date -u -d yesterday +%Y)

echo "=== $(date -u '+%Y-%m-%d %H:%M:%S UTC') Starting daily pipeline ===" >> "$LOG"

# Step 1: Data sync
echo "--- datasync ---" >> "$LOG"
python3 "$TS/datasync-snowflux-pea.py" >> "$LOG" 2>&1
echo "--- datasync done (exit $?) ---" >> "$LOG"

# Step 2: Julia processing (resume mode — skips already-processed dates)
for sensor in SFC LOWER UPPER BOTTOM; do
    echo "--- Processing $sensor ---" >> "$LOG"
    julia --project="$JL" "$JL/scripts/run_sensor.jl" "$sensor" >> "$LOG" 2>&1 \
        && echo "--- $sensor done ---" >> "$LOG" \
        || echo "--- $sensor FAILED (exit $?) ---" >> "$LOG"
done

echo "=== $(date -u '+%Y-%m-%d %H:%M:%S UTC') Pipeline complete ===" >> "$LOG"

#!/bin/bash
# Launch the Peddy H2O-reference rerun for LOWER and UPPER for one year, as parallel
# month-aligned chunks (one Julia process each, --restart) plus one --slow-only run per
# sensor that writes the cleaned OneMin slow data. All processes are detached (nohup).
#
#   bash rerun_peddy_h2o.sh 2026   -> output in processed_HF_rerun/ and processed_LF_rerun/ (swap in later)
#   bash rerun_peddy_h2o.sh 2025   -> output in 2025/processed_HF and 2025/processed_LF
#
# Logs: /data/disk1/shared/PEA/logs/peddy_<year>_<sensor>_{slow,<from>}.log
# Progress: find <PEA_HF_OUT>/<sensor> -name '*Fastdata_proc*' | wc -l

YEAR=${1:?usage: rerun_peddy_h2o.sh 2025|2026}
PEA=/data/disk1/shared/PEA
JL=$PEA/transfer_scripts/DataProcessingScriptsJulia
LOGS=$PEA/logs
mkdir -p "$LOGS"

case "$YEAR" in
  2026)
    export PEA_INPUT_BASE=$PEA/data
    export PEA_HF_OUT=$PEA/processed_HF_rerun
    export PEA_LF_OUT=$PEA/processed_LF_rerun
    CHUNKS="2026-01-01:2026-03-31 2026-04-01:2026-06-30 2026-07-01:2026-12-31"
    ;;
  2025)
    export PEA_INPUT_BASE=$PEA/2025/converted
    export PEA_HF_OUT=$PEA/2025/processed_HF
    export PEA_LF_OUT=$PEA/2025/processed_LF
    CHUNKS="2025-02-01:2025-04-30 2025-05-01:2025-12-31"
    ;;
  *) echo "unknown year $YEAR"; exit 2;;
esac
export PEA_YEAR=$YEAR

cd "$JL" || exit 1
for S in LOWER UPPER; do
  nohup julia --project=. scripts/run_sensor.jl "$S" --slow-only > "$LOGS/peddy_${YEAR}_${S}_slow.log" 2>&1 &
  echo "launched $S slow-only (pid $!)"
  for C in $CHUNKS; do
    FROM=${C%%:*}; TO=${C##*:}
    nohup julia --project=. scripts/run_sensor.jl "$S" --restart --no-save-slow --from "$FROM" --to "$TO" \
      > "$LOGS/peddy_${YEAR}_${S}_${FROM}.log" 2>&1 &
    echo "launched $S $FROM..$TO (pid $!)"
  done
done

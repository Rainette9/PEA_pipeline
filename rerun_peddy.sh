#!/bin/bash
# Launch a full Peddy rerun (--restart) for one year and a list of sensors as detached,
# month-aligned parallel chunks (one Julia process each) plus one --slow-only run per sensor
# that writes the cleaned OneMin slow data. Output goes to a separate *_rerun tree; swap it
# into place afterwards with swap_in_rerun.sh (so the daily cron keeps running meanwhile).
#
#   bash rerun_peddy.sh 2026                      # all four sensors, raw from $PEA_ROOT/data
#   bash rerun_peddy.sh 2025 "SFC LOWER UPPER"    # raw from $PEA_ROOT/2025/converted
#
# Environment: PEA_ROOT (default /data/disk1/shared/PEA), CHUNKS (default 3 chunks per year),
#   PEA_INPUT_BASE / PEA_HF_OUT / PEA_LF_OUT override the per-year defaults below,
#   EXTRA="--diag_margin=0 ..." extra run_sensor.jl options.
# Logs: $PEA_ROOT/logs/peddy_<year>_<sensor>_{slow,<from>}.log
# Progress: find <PEA_HF_OUT>/<sensor> -name '*Fastdata_proc*' | wc -l
# Peddy version: whatever DataProcessingScriptsJulia/Manifest.toml pins (v3 = fix_licor fe0c4c3).

YEAR=${1:?usage: rerun_peddy.sh YEAR ["SENSORS"]}
SENSORS=${2:-"SFC LOWER UPPER BOTTOM"}
PEA_ROOT=${PEA_ROOT:-/data/disk1/shared/PEA}
TS=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
JL=$TS/DataProcessingScriptsJulia
LOGS=$PEA_ROOT/logs
mkdir -p "$LOGS"

case "$YEAR" in
  2025)
    export PEA_INPUT_BASE=${PEA_INPUT_BASE:-$PEA_ROOT/2025/converted}
    export PEA_HF_OUT=${PEA_HF_OUT:-$PEA_ROOT/2025/processed_HF_rerun}
    export PEA_LF_OUT=${PEA_LF_OUT:-$PEA_ROOT/2025/processed_LF_rerun}
    ;;
  *)
    export PEA_INPUT_BASE=${PEA_INPUT_BASE:-$PEA_ROOT/data}
    export PEA_HF_OUT=${PEA_HF_OUT:-$PEA_ROOT/processed_HF_rerun}
    export PEA_LF_OUT=${PEA_LF_OUT:-$PEA_ROOT/processed_LF_rerun}
    ;;
esac
export PEA_YEAR=$YEAR
CHUNKS=${CHUNKS:-"$YEAR-01-01:$YEAR-04-30 $YEAR-05-01:$YEAR-08-31 $YEAR-09-01:$YEAR-12-31"}

echo "rerun_peddy.sh year=$YEAR sensors=[$SENSORS] input=$PEA_INPUT_BASE hf=$PEA_HF_OUT lf=$PEA_LF_OUT"
echo "  Peddy: $(grep -A3 'deps.Peddy' "$JL/Manifest.toml" | grep git-tree-sha1 | cut -d'"' -f2)"
cd "$JL" || exit 1
for S in $SENSORS; do
  nohup julia --project=. scripts/run_sensor.jl "$S" --slow-only $EXTRA > "$LOGS/peddy_${YEAR}_${S}_slow.log" 2>&1 &
  echo "launched $S slow-only (pid $!)"
  for C in $CHUNKS; do
    FROM=${C%%:*}; TO=${C##*:}
    nohup julia --project=. scripts/run_sensor.jl "$S" --restart --no-save-slow --from "$FROM" --to "$TO" $EXTRA \
      > "$LOGS/peddy_${YEAR}_${S}_${FROM}.log" 2>&1 &
    echo "launched $S $FROM..$TO (pid $!)"
  done
done

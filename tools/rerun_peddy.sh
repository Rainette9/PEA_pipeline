#!/bin/bash
# Launch a full Peddy rerun (--restart) for one year and a list of sensors as detached,
# month-aligned parallel chunks (one Julia process each) plus one --slow-only run per sensor
# that writes the cleaned OneMin slow data. Output goes to a separate *_rerun tree next to the
# normal one; swap it into place afterwards with tools/swap_in_rerun.sh (so the daily cron keeps
# running meanwhile).
#
#   bash tools/rerun_peddy.sh 2026                                             # all four sensors, raw from $PEA_INPUT_BASE
#   PEA_INPUT_BASE=$PEA_ROOT/2025/converted bash tools/rerun_peddy.sh 2025 "SFC LOWER UPPER"   # 2025 logger-card raw
#
# Environment (see pea_env.sh): PEA_ROOT, PEA_INPUT_BASE (raw root), PEA_HF_OUT / PEA_LF_OUT (the
#   normal output trees; the rerun writes to <tree>_rerun), PEA_LOGS, CHUNKS (default 3 per year),
#   EXTRA="--diag_margin=0 ..." extra run_sensor.jl options.
# Logs: $PEA_LOGS/peddy_<year>_<sensor>_{slow,<from>}.log
# Progress: find ${PEA_HF_OUT}_rerun/<sensor> -name '*Fastdata_proc*' | wc -l
# Peddy version: whatever DataProcessingScriptsJulia/Manifest.toml pins (v3 = fix_licor fe0c4c3).

YEAR=${1:?usage: rerun_peddy.sh YEAR ["SENSORS"]}
SENSORS=${2:-"SFC LOWER UPPER BOTTOM"}
. "$(dirname "${BASH_SOURCE[0]}")/../pea_env.sh"
export PEA_YEAR=$YEAR
export PEA_HF_OUT=${PEA_HF_OUT}_rerun
export PEA_LF_OUT=${PEA_LF_OUT}_rerun
CHUNKS=${CHUNKS:-"$YEAR-01-01:$YEAR-04-30 $YEAR-05-01:$YEAR-08-31 $YEAR-09-01:$YEAR-12-31"}

echo "rerun_peddy.sh year=$YEAR sensors=[$SENSORS] input=$PEA_INPUT_BASE hf=$PEA_HF_OUT lf=$PEA_LF_OUT"
echo "  Peddy: $(grep -A3 'deps.Peddy' "$JL/Manifest.toml" | grep git-tree-sha1 | cut -d'"' -f2)"
cd "$JL" || exit 1
for S in $SENSORS; do
  nohup julia --project=. scripts/run_sensor.jl "$S" --slow-only $EXTRA > "$PEA_LOGS/peddy_${YEAR}_${S}_slow.log" 2>&1 &
  echo "launched $S slow-only (pid $!)"
  for C in $CHUNKS; do
    FROM=${C%%:*}; TO=${C##*:}
    nohup julia --project=. scripts/run_sensor.jl "$S" --restart --no-save-slow --from "$FROM" --to "$TO" $EXTRA \
      > "$PEA_LOGS/peddy_${YEAR}_${S}_${FROM}.log" 2>&1 &
    echo "launched $S $FROM..$TO (pid $!)"
  done
done

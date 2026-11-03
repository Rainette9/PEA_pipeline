#!/bin/bash
# Swap a Peddy rerun (made by rerun_peddy.sh) into place and archive the previous output.
#   <HF>/<S>/<YEAR>??        -> $ARCHIVE_ROOT/processed_HF_archive_<STAMP>/<S>/  (old files kept)
#   <HF>_rerun/<S>/<YEAR>??  -> <HF>/<S>/
#   same for <LF> / <LF>_rerun -> processed_LF_archive_<STAMP>
# Eddypro_output/ and biomet/ stay where they are (run_eddypro.sh archives EddyPro files itself
# via ARCHIVE_DIR). For the current year one resume run per sensor then fills the days that arrived
# while the rerun was running. Refuses to run while a Julia sensor script is active or close to the
# daily cron.
#
#   nohup bash tools/swap_in_rerun.sh 2026 > $PEA_ROOT/logs/swap_2026.log 2>&1 &   # all four sensors
#   bash tools/swap_in_rerun.sh 2025 "SFC LOWER UPPER"
# Environment (see pea_env.sh): PEA_ROOT, PEA_HF_OUT / PEA_LF_OUT (the normal trees), PEA_LOGS,
#   ARCHIVE_ROOT (default $PEA_ROOT/archive), STAMP (default today, YYYYMMDD),
#   RESUME=1/0 (default 1 for the current year, 0 for past years).
set -u
YEAR=${1:?usage: swap_in_rerun.sh YEAR ["SENSORS"]}
SENSORS=${2:-"SFC LOWER UPPER BOTTOM"}
. "$(dirname "${BASH_SOURCE[0]}")/../pea_env.sh"
HF=$PEA_HF_OUT; LF=$PEA_LF_OUT
STAMP=${STAMP:-$(date -u +%Y%m%d)}
RESUME=${RESUME:-$([ "$YEAR" = "$(date -u +%Y)" ] && echo 1 || echo 0)}
ARCHIVE_ROOT=${ARCHIVE_ROOT:-$PEA_ROOT/archive}
ARCH=$ARCHIVE_ROOT/processed_HF_archive_$STAMP
ARCHLF=$ARCHIVE_ROOT/processed_LF_archive_$STAMP

if pgrep -f 'julia.*scripts/run_sensor\.jl' > /dev/null; then
    echo "Julia sensor scripts are running — not swapping."; pgrep -af 'julia.*scripts/run_sensor'; exit 1
fi
H=$(date -u +%H%M)
if [ "$H" -ge 2355 ] || [ "$H" -lt 0045 ]; then echo "Too close to the daily cron — try later."; exit 1; fi

echo "=== $(date -u) swap start: year=$YEAR sensors=[$SENSORS] hf=$HF lf=$LF archive stamp=$STAMP"
for s in $SENSORS; do
    n_new=$(ls -d ${HF}_rerun/$s/${YEAR}?? 2>/dev/null | wc -l)
    [ "$n_new" -gt 0 ] || { echo "no rerun output for $s under ${HF}_rerun — abort"; exit 1; }
    mkdir -p "$ARCH/$s" "$ARCHLF/$s" "$HF/$s" "$LF/$s"
    for d in $HF/$s/${YEAR}??;        do [ -d "$d" ] && mv -v "$d" "$ARCH/$s/"; done
    for d in ${HF}_rerun/$s/${YEAR}??; do mv -v "$d" "$HF/$s/"; done
    for d in $LF/$s/${YEAR}??;        do [ -d "$d" ] && mv -v "$d" "$ARCHLF/$s/"; done
    for d in ${LF}_rerun/$s/${YEAR}??; do [ -d "$d" ] && mv -v "$d" "$LF/$s/"; done
    echo "$s: $(find $HF/$s -name '*Fastdata_proc*' | wc -l) hourly files now in $HF/$s"
done
echo "=== $(date -u) swap done"
if [ "$RESUME" = 1 ]; then
    echo "resume runs to fill days that arrived meanwhile"
    export PEA_YEAR=$YEAR
    for s in $SENSORS; do
        julia --project="$JL" "$JL/scripts/run_sensor.jl" "$s" > "$PEA_LOGS/swap_resume_${YEAR}_$s.log" 2>&1 \
            && echo "$s resume done" || echo "$s resume FAILED (see $PEA_LOGS/swap_resume_${YEAR}_$s.log)"
    done
fi
echo "=== $(date -u) all done"

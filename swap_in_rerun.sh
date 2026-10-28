#!/bin/bash
# Swap a Peddy rerun (made by rerun_peddy.sh) into place and archive the previous output.
#   <HF>/<S>/<YEAR>??        -> $PEA_ROOT/archive/[2025_]processed_HF_archive_<STAMP>/<S>/  (old files kept)
#   <HF>_rerun/<S>/<YEAR>??  -> <HF>/<S>/
#   same for <LF> / <LF>_rerun -> archive/[2025_]processed_LF_archive_<STAMP>
# Eddypro_output/ and biomet/ stay where they are (run_eddypro_months.sh archives EddyPro files itself
# via ARCHIVE_DIR). For the current year one resume run per sensor then fills the days that arrived
# while the rerun was running. Refuses to run while a Julia sensor script is active or close to the
# daily cron.
#
#   nohup bash swap_in_rerun.sh 2026 > logs/swap_2026.log 2>&1 &        # all four sensors
#   bash swap_in_rerun.sh 2025 "SFC LOWER UPPER"                        # 2025 tree ($PEA_ROOT/2025/...)
# Environment: PEA_ROOT, ARCHIVE_ROOT (default $PEA_ROOT/archive), STAMP (default today, YYYYMMDD),
#   RESUME=0 to skip the resume runs.
set -u
YEAR=${1:?usage: swap_in_rerun.sh YEAR ["SENSORS"]}
SENSORS=${2:-"SFC LOWER UPPER BOTTOM"}
PEA_ROOT=${PEA_ROOT:-/data/disk1/shared/PEA}
TS=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
JL=$TS/DataProcessingScriptsJulia
STAMP=${STAMP:-$(date -u +%Y%m%d)}
if [ "$YEAR" = 2025 ]; then BASE=$PEA_ROOT/2025; RESUME=${RESUME:-0}; else BASE=$PEA_ROOT; RESUME=${RESUME:-1}; fi
HF=$BASE/processed_HF; LF=$BASE/processed_LF
ARCHIVE_ROOT=${ARCHIVE_ROOT:-$PEA_ROOT/archive}
ARCH=$ARCHIVE_ROOT/$([ "$YEAR" = 2025 ] && echo 2025_)processed_HF_archive_$STAMP
ARCHLF=$ARCHIVE_ROOT/$([ "$YEAR" = 2025 ] && echo 2025_)processed_LF_archive_$STAMP

if pgrep -f 'scripts/run_(sensor|LOWER|UPPER|SFC|BOTTOM)\.jl' > /dev/null; then
    echo "Julia sensor scripts are running — not swapping."; pgrep -af 'scripts/run_'; exit 1
fi
H=$(date -u +%H%M)
if [ "$H" -ge 2355 ] || [ "$H" -lt 0045 ]; then echo "Too close to the daily cron — try later."; exit 1; fi

echo "=== $(date -u) swap start: year=$YEAR sensors=[$SENSORS] tree=$BASE archive stamp=$STAMP"
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
    cd "$JL" || exit 1
    export PEA_INPUT_BASE=$PEA_ROOT/data PEA_HF_OUT=$HF PEA_LF_OUT=$LF PEA_YEAR=$YEAR
    for s in $SENSORS; do
        julia --project=. scripts/run_$s.jl > "$PEA_ROOT/logs/swap_resume_${YEAR}_$s.log" 2>&1 \
            && echo "$s resume done" || echo "$s resume FAILED (see logs/swap_resume_${YEAR}_$s.log)"
    done
fi
echo "=== $(date -u) all done"

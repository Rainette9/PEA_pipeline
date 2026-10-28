#!/bin/bash
# Phase 3 of the Oct-2026 H2O rerun: swap the rerun 2026 LOWER/UPPER output into production.
#   processed_HF/<S>/2026??  -> processed_HF_archive_<date>/<S>/      (old hourly files kept)
#   processed_HF_rerun/<S>/2026?? -> processed_HF/<S>/
#   same for processed_LF / processed_LF_rerun -> processed_LF_archive_<date>
# Eddypro_output/ and biomet/ stay where they are. Then one resume run per sensor fills days that
# arrived while the rerun was running. Refuses to run while a Julia sensor script is active.
# Usage: nohup bash swap_in_rerun_2026.sh > logs/swap_2026.log 2>&1 &
set -u
PEA=/data/disk1/shared/PEA
JL=$PEA/transfer_scripts/DataProcessingScriptsJulia
STAMP=${STAMP:-20261001}
ARCH=$PEA/processed_HF_archive_$STAMP
ARCHLF=$PEA/processed_LF_archive_$STAMP

if pgrep -f 'scripts/run_(sensor|LOWER|UPPER|SFC|BOTTOM)\.jl' > /dev/null; then
    echo "Julia sensor scripts are running — not swapping."; pgrep -af 'scripts/run_' ; exit 1
fi
H=$(date -u +%H%M)
if [ "$H" -ge 2355 ] || [ "$H" -lt 0045 ]; then echo "Too close to the 00:03 UTC daily cron — try later."; exit 1; fi

echo "=== $(date -u) swap start"
for s in LOWER UPPER; do
    n_new=$(ls -d $PEA/processed_HF_rerun/$s/2026?? 2>/dev/null | wc -l)
    [ "$n_new" -gt 0 ] || { echo "no rerun output for $s — abort"; exit 1; }
    mkdir -p "$ARCH/$s" "$ARCHLF/$s"
    for d in $PEA/processed_HF/$s/2026??; do [ -d "$d" ] && mv -v "$d" "$ARCH/$s/"; done
    for d in $PEA/processed_HF_rerun/$s/2026??; do mv -v "$d" "$PEA/processed_HF/$s/"; done
    for d in $PEA/processed_LF/$s/2026??; do [ -d "$d" ] && mv -v "$d" "$ARCHLF/$s/"; done
    for d in $PEA/processed_LF_rerun/$s/2026??; do [ -d "$d" ] && mv -v "$d" "$PEA/processed_LF/$s/"; done
    echo "$s: $(find $PEA/processed_HF/$s -name '*Fastdata_proc*' | wc -l) hourly files now in production"
done
echo "=== $(date -u) swap done; resume runs to fill days that arrived meanwhile"
cd "$JL" || exit 1
for s in LOWER UPPER; do
    julia --project=. scripts/run_$s.jl > "$PEA/logs/swap_resume_$s.log" 2>&1 && echo "$s resume done" || echo "$s resume FAILED (see logs/swap_resume_$s.log)"
done
echo "=== $(date -u) all done"

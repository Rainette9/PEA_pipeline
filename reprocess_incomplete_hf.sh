#!/bin/bash
# Delete processed_HF output for days where source data is now complete
# but processing was done against a partial daily file (2-hour stub).
# After deletion, re-run the Julia scripts in resume mode to fill gaps.

HF=${PEA_ROOT:-/data/disk1/shared/PEA}/processed_HF
DRY=${DRY:-0}  # set DRY=1 to preview without deleting

delete_day() {
    local level=$1 date=$2
    local yyyymm=${date:0:4}${date:5:2}
    local dir="${HF}/${level}/${yyyymm}"
    local prefix="${level}_Fastdata_proc_${date}_"
    mapfile -t files < <(find "$dir" -maxdepth 1 -name "${prefix}*.dat" 2>/dev/null | sort)
    if [ ${#files[@]} -gt 0 ]; then
        echo "  rm ${level}/${yyyymm}/${prefix}*.dat  (${#files[@]} files)"
        [ "$DRY" = "0" ] && rm -f "${files[@]}"
    fi
}

echo "=== BOTTOM ==="
for d in 2026-03-30 2026-03-31 \
          2026-04-01 2026-04-02 2026-04-03 2026-04-04 2026-04-05 \
          2026-04-08 2026-04-09 2026-04-10 2026-04-11 \
          2026-04-15 \
          2026-04-18 2026-04-19 2026-04-20 \
          2026-04-24; do
    delete_day BOTTOM $d
done

echo "=== LOWER ==="
for d in 2026-03-30 2026-03-31 \
          2026-04-01 2026-04-02 2026-04-03 2026-04-04 2026-04-05 \
          2026-04-08 2026-04-09 2026-04-10 2026-04-11 \
          2026-04-12 2026-04-13 2026-04-14 2026-04-15 \
          2026-04-18 2026-04-19 \
          2026-04-22 2026-04-23 2026-04-24 2026-04-25 \
          2026-06-12 2026-06-13; do
    delete_day LOWER $d
done

echo "=== UPPER ==="
for d in 2026-03-30 2026-03-31 \
          2026-04-01 2026-04-02 2026-04-03 2026-04-04 2026-04-05 2026-04-06 \
          2026-04-08 2026-04-09 2026-04-10 2026-04-11 \
          2026-04-12 2026-04-13 2026-04-14 2026-04-15 \
          2026-04-16 2026-04-17 2026-04-18 2026-04-19 2026-04-20 \
          2026-04-21 2026-04-22 2026-04-23 2026-04-24 2026-04-25 \
          2026-04-30 \
          2026-05-24 2026-05-25 2026-05-26 2026-05-27 \
          2026-05-29 2026-05-30 \
          2026-06-02 2026-06-03 \
          2026-06-05 2026-06-06 2026-06-07 \
          2026-06-09 2026-06-10 \
          2026-06-12 2026-06-13; do
    delete_day UPPER $d
done

echo ""
echo "Done. Now re-run the Julia scripts:"
echo "  julia --project=DataProcessingScriptsJulia DataProcessingScriptsJulia/scripts/run_BOTTOM.jl"
echo "  julia --project=DataProcessingScriptsJulia DataProcessingScriptsJulia/scripts/run_LOWER.jl"
echo "  julia --project=DataProcessingScriptsJulia DataProcessingScriptsJulia/scripts/run_UPPER.jl"

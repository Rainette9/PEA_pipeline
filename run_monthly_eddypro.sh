#!/bin/bash
# Monthly cron: EddyPro for the previous calendar month, all sensors
# (thin wrapper around run_eddypro_months.sh; 5-min averaging, biomet from processed_LF).
FIRST_DAY=$(date -d "$(date +%Y-%m-01) -1 month" +%Y-%m-%d)   # e.g. 2026-02-01
export MONTHS=$(date -d "$FIRST_DAY" +%Y%m)                   # e.g. 202602
PEA_ROOT=${PEA_ROOT:-/data/disk1/shared/PEA}
export PEA_ROOT
export LOG=$PEA_ROOT/data/eddypro_monthly.log
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_eddypro_months.sh"

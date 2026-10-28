#!/bin/bash
# One-time bulk EddyPro run for past months (thin wrapper around run_eddypro_months.sh).
# Usage: MONTHS="202601 202602" nohup bash run_bulk_eddypro.sh &
# All run_eddypro_months.sh env vars apply (HF_BASE, LF_BASE, SENSORS, TAG, AVRG_LEN, ARCHIVE_DIR, PARALLEL, LOG).
PEA_ROOT=${PEA_ROOT:-/data/disk1/shared/PEA}
export PEA_ROOT
export LOG=${LOG:-$PEA_ROOT/data/eddypro_bulk.log}
if [ -z "$MONTHS" ]; then
    echo "MONTHS is required, e.g. MONTHS=\"202601 202602\"" >&2
    exit 2
fi
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_eddypro_months.sh"

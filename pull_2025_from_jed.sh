#!/bin/bash
# Pull the 2025 inputs needed for the Peddy/EddyPro rerun from jed into the local 2025/ tree.
# Idempotent (rsync). Usage: nohup bash transfer_scripts/pull_2025_from_jed.sh > logs/rsync_2025.log 2>&1 &
set -u
J='engbers@jed.hpc.epfl.ch:/export/cryos/CRYOS/Projects/Antarctica/PrincessElisabeth/Season_2025-2026/DATA/MET'
SSH='ssh -i /home/cryos/.ssh/epfl -o IdentitiesOnly=yes -o BatchMode=yes'
L=/data/disk1/shared/PEA/2025
echo "=== $(date -u) start"
# 1. raw converted fast+slow for LOWER/UPPER (Peddy rerun)
rsync -a --info=progress2 -e "$SSH" \
  "$J/converted/20251226_LOWER" "$J/converted/20251226_UPPER" \
  "$J/converted/20260113_LOWER" "$J/converted/20260113_UPPER" \
  "$L/converted/" && echo "converted OK" || echo "converted FAILED"
# 2. processed slow data (biomet) for all sensors
rsync -a --info=progress2 -e "$SSH" \
  "$J/processed_LF/2025/SFC" "$J/processed_LF/2025/BOTTOM" "$J/processed_LF/2025/UPPER" "$J/processed_LF/2025/LOWER" \
  "$L/processed_LF/" && echo "processed_LF OK" || echo "processed_LF FAILED"
# 3. comparison sample of the old fixed LOWER/UPPER files (3 days)
rsync -a --info=progress2 -e "$SSH" \
  --include='*/' --include='*_2025-03-1[0-2]_*.dat' --exclude='*' \
  "$J/processed_HF/2025/LOWER" "$J/processed_HF/2025/UPPER" \
  "$L/processed_HF_jed_sample/" && echo "sample OK" || echo "sample FAILED"
# 4. processed HF for SFC/BOTTOM (EddyPro-only rerun), without old EddyPro outputs
rsync -a --info=progress2 -e "$SSH" \
  --exclude='Eddypro_output*' --exclude='Eddypro_ouput*' --exclude='plots' --exclude='*.eddypro' --exclude='*.metadata' --exclude='processing_log_*' \
  "$J/processed_HF/2025/SFC" "$J/processed_HF/2025/BOTTOM" \
  "$L/processed_HF/" && echo "processed_HF SFC/BOTTOM OK" || echo "processed_HF SFC/BOTTOM FAILED"
echo "=== $(date -u) done"

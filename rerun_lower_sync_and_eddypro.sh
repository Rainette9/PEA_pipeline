#!/bin/bash
# Restart script for LOWER timestamp-shift follow-up tasks.
# Safe to run even if the tasks are partially complete (rsync and EddyPro are both idempotent).
#
# Usage (from any terminal, detached from Claude):
#   nohup bash /data/disk1/shared/PEA/transfer_scripts/rerun_lower_sync_and_eddypro.sh &
#   tail -f /data/disk1/shared/PEA/data/rerun_lower.log

LOG=/data/disk1/shared/PEA/data/rerun_lower.log

EDDYPRO_BIN=/data/disk1/shared/PEA/transfer_scripts/eddypro/eddypro-engine/bin/linux
EDDYPRO_ENGINE=/data/disk1/shared/PEA/transfer_scripts/eddypro/eddypro-engine/
SCRIPTS_DIR=/data/disk1/shared/PEA/transfer_scripts/eddypro/eddypro_scripts

SSH_KEY="$HOME/.ssh/epfl"
REMOTE_USER="engbers"
REMOTE_HOST="jed.hpc.epfl.ch"
BASE_REMOTE="/export/cryos/CRYOS/Projects/Antarctica/PrincessElisabeth/Season_2025-2026/DATA/MET"

echo "============================================================" | tee "$LOG"
echo "Started at $(date -u '+%Y-%m-%d %H:%M:%S UTC')" | tee -a "$LOG"
echo "============================================================" | tee -a "$LOG"

# ── 1. Sync processed_HF and processed_LF to jed ─────────────────────────────

for label in processed_HF processed_LF; do
    echo "" | tee -a "$LOG"
    echo "--- Syncing $label to jed ---" | tee -a "$LOG"
    rsync -avz \
        -e "ssh -i ${SSH_KEY} -o IdentitiesOnly=yes" \
        "/data/disk1/shared/PEA/${label}/" \
        "${REMOTE_USER}@${REMOTE_HOST}:${BASE_REMOTE}/${label}/2026/" \
        >> "$LOG" 2>&1
    if [ $? -eq 0 ]; then
        echo "  ✓ $label synced" | tee -a "$LOG"
    else
        echo "  ✗ $label sync FAILED" | tee -a "$LOG"
    fi
done

# ── 2. EddyPro re-run for LOWER 202603 202604 202605 ─────────────────────────

cd "$SCRIPTS_DIR"

for MONTH_STR in 202603 202604 202605; do
    YEAR=${MONTH_STR:0:4}
    MON=${MONTH_STR:4:2}
    FIRST_DAY="${YEAR}-${MON}-01"
    LAST_DAY=$(date -d "${YEAR}-${MON}-01 +1 month -1 day" +%Y-%m-%d)

    echo "" | tee -a "$LOG"
    echo "--- EddyPro LOWER $MONTH_STR ($FIRST_DAY → $LAST_DAY) ---" | tee -a "$LOG"

    sensor=LOWER
    TMP_FILE="PEA_${sensor}_${MONTH_STR}.eddypro"
    OUT_PATH="/data/disk1/shared/PEA/processed_HF/${sensor}/Eddypro_output/${MONTH_STR}"
    mkdir -p "$OUT_PATH"

    sed \
        -e "s|^file_name=.*|file_name=${SCRIPTS_DIR}/${TMP_FILE}|" \
        -e "s|^project_id=.*|project_id=PEA_${sensor}_${MONTH_STR}|" \
        -e "s|^pr_subset=.*|pr_subset=1|" \
        -e "s|^pr_start_date=.*|pr_start_date=${FIRST_DAY}|" \
        -e "s|^pr_end_date=.*|pr_end_date=${LAST_DAY}|" \
        -e "s|^pf_start_date=.*|pf_start_date=${FIRST_DAY}|" \
        -e "s|^pf_end_date=.*|pf_end_date=${LAST_DAY}|" \
        -e "s|^to_start_date=.*|to_start_date=${FIRST_DAY}|" \
        -e "s|^to_end_date=.*|to_end_date=${LAST_DAY}|" \
        -e "s|^out_path=.*|out_path=${OUT_PATH}|" \
        -e "s|^sa_bin_spectra=.*|sa_bin_spectra=${OUT_PATH}/eddypro_binned_cospectra|" \
        -e "s|^sa_full_spectra=.*|sa_full_spectra=${OUT_PATH}/eddypro_full_cospectra|" \
        "PEA_${sensor}.eddypro" > "$TMP_FILE"

    "$EDDYPRO_BIN/eddypro_rp" -s linux -e "$EDDYPRO_ENGINE" "$TMP_FILE" >> "$LOG" 2>&1 \
        && echo "  eddypro_rp done" | tee -a "$LOG" \
        || { echo "  eddypro_rp FAILED — skipping fcc" | tee -a "$LOG"; rm -f "$TMP_FILE"; continue; }

    ESSENTIALS=$(find "$OUT_PATH" -maxdepth 1 -name "eddypro_*_fluxnet_*.csv" | sort | tail -1)
    if [ -z "$ESSENTIALS" ]; then
        echo "  ERROR: no essentials file — skipping fcc" | tee -a "$LOG"
        rm -f "$TMP_FILE"; continue
    fi
    echo "  Essentials: $ESSENTIALS" | tee -a "$LOG"
    sed -i "s|^ex_file=.*|ex_file=${ESSENTIALS}|" "$TMP_FILE"

    "$EDDYPRO_BIN/eddypro_fcc" -s linux -e "$EDDYPRO_ENGINE" "$TMP_FILE" >> "$LOG" 2>&1 \
        && echo "  eddypro_fcc done" | tee -a "$LOG" \
        || echo "  eddypro_fcc FAILED" | tee -a "$LOG"

    rm -f "$TMP_FILE"
done

echo "" | tee -a "$LOG"
echo "============================================================" | tee -a "$LOG"
echo "Finished at $(date -u '+%Y-%m-%d %H:%M:%S UTC')" | tee -a "$LOG"
echo "============================================================" | tee -a "$LOG"

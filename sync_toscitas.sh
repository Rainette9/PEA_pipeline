
#!/bin/bash
 
# ============================================================
# sync_to_jed.sh
# Syncs processed_HF, processed_LF, and raw data to SCITAS jed
# Usage: ./sync_to_jed.sh
# ============================================================
 
# --- Configuration ---
REMOTE_USER="engbers"
REMOTE_HOST="jed.hpc.epfl.ch"
SSH_KEY="$HOME/.ssh/epfl"
YEAR=$(date +%Y)
 
BASE_REMOTE="/export/cryos/CRYOS/Projects/Antarctica/PrincessElisabeth/Season_2025-2026/DATA/MET"
 
# ============================================================
# Helper function
# ============================================================
sync_dir() {
    local LABEL="$1"
    local LOCAL="$2"
    local REMOTE="$3"
 
    echo ""
    echo "------------------------------------------------------------"
    echo "Syncing: $LABEL"
    echo "  FROM: $LOCAL"
    echo "  TO:   ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE}"
    echo "------------------------------------------------------------"
 
    rsync -avz --progress \
        -e "ssh -i ${SSH_KEY} -o IdentitiesOnly=yes" \
        "${LOCAL}" \
        "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE}"
 
    if [ $? -eq 0 ]; then
        echo "✓ $LABEL synced successfully"
    else
        echo "✗ $LABEL sync FAILED"
        ERRORS=$((ERRORS + 1))
    fi
}
 
# ============================================================
# Start
# ============================================================
ERRORS=0
echo "============================================================"
echo "Starting sync at $(date)"
echo "============================================================"
 
# --- 1. processed_HF (all subdirs: BOTTOM, LOWER, SFC, UPPER) ---
sync_dir \
    "processed_HF" \
    "/data/disk1/shared/PEA/processed_HF/" \
    "${BASE_REMOTE}/processed_HF/${YEAR}/"
 
# --- 2. processed_LF (all subdirs: BOTTOM, LOWER, SFC, UPPER) ---
sync_dir \
    "processed_LF" \
    "/data/disk1/shared/PEA/processed_LF/" \
    "${BASE_REMOTE}/processed_LF/${YEAR}/"
 
# --- 3. data/BOTTOM ---
sync_dir \
    "data/BOTTOM" \
    "/data/disk1/shared/PEA/data/BOTTOM/" \
    "${BASE_REMOTE}/data_transfer/BOTTOM/"
 
# --- 4. data/LOWER ---
sync_dir \
    "data/LOWER" \
    "/data/disk1/shared/PEA/data/LOWER/" \
    "${BASE_REMOTE}/data_transfer/LOWER/"
 
# --- 5. data/SFC ---
sync_dir \
    "data/SFC" \
    "/data/disk1/shared/PEA/data/SFC/" \
    "${BASE_REMOTE}/data_transfer/SFC/"
 
# --- 6. data/UPPER ---
sync_dir \
    "data/UPPER" \
    "/data/disk1/shared/PEA/data/UPPER/" \
    "${BASE_REMOTE}/data_transfer/UPPER/"
 
# ============================================================
# Summary
# ============================================================
echo ""
echo "============================================================"
if [ $ERRORS -eq 0 ]; then
    echo "✓ All syncs completed successfully at $(date)"
else
    echo "✗ Sync finished with $ERRORS failure(s) at $(date)"
    exit 1
fi
echo "============================================================"

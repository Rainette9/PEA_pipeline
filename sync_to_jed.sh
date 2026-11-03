#!/bin/bash
# Copy the processed and raw data to jed (EPFL SCITAS) with rsync. Cron: every 10 days.
#
#   bash sync_to_jed.sh              # sync
#   DRY_RUN=1 bash sync_to_jed.sh    # rsync -n: show what would be copied, change nothing
#
# Paths from pea_env.sh (PEA_ROOT, PEA_HF_OUT, PEA_LF_OUT, PEA_INPUT_BASE, PEA_LOGS).
# The local trees are mirrored 1:1 (no year folder on the remote side, so January does not
# start a new copy of everything):
#   $PEA_HF_OUT/      -> $REMOTE_BASE/v3/processed_HF/       (Peddy hourly files + EddyPro output)
#   $PEA_LF_OUT/      -> $REMOTE_BASE/v3/processed_LF/       (1-min slow data + biomet files)
#   $PEA_INPUT_BASE/<S>/ -> $REMOTE_BASE/data_transfer/<S>/  (raw daily logger files, as before)
# Nothing is deleted on the remote side. Log: $PEA_LOGS/sync_jed.log (also written by this script).
. "$(dirname "${BASH_SOURCE[0]}")/pea_env.sh"

REMOTE_USER=${REMOTE_USER:-engbers}
REMOTE_HOST=${REMOTE_HOST:-jed.hpc.epfl.ch}
SSH_KEY=${SSH_KEY:-$HOME/.ssh/epfl}
REMOTE_BASE=${REMOTE_BASE:-/export/cryos/CRYOS/Projects/Antarctica/PrincessElisabeth/Season_2025-2026/DATA/MET}
LOG=${LOG:-$PEA_LOGS/sync_jed.log}
SSH="ssh -i $SSH_KEY -o IdentitiesOnly=yes -o BatchMode=yes"
RSYNC_OPTS=(-az --no-group --no-perms --omit-dir-times)
[ "${DRY_RUN:-0}" = 1 ] && RSYNC_OPTS+=(-n -v)

# "local_dir remote_dir" pairs
PAIRS=(
    "$PEA_HF_OUT $REMOTE_BASE/v3/processed_HF"
    "$PEA_LF_OUT $REMOTE_BASE/v3/processed_LF"
)
for s in SFC BOTTOM LOWER UPPER; do
    PAIRS+=("$PEA_INPUT_BASE/$s $REMOTE_BASE/data_transfer/$s")
done

log() { echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') $*" | tee -a "$LOG"; }

log "=== sync to $REMOTE_USER@$REMOTE_HOST:$REMOTE_BASE started${DRY_RUN:+ (dry run)} ==="
# create the remote folders once (rsync does not create missing parents)
if [ "${DRY_RUN:-0}" != 1 ]; then
    $SSH "$REMOTE_USER@$REMOTE_HOST" mkdir -p "$REMOTE_BASE/v3/processed_HF" "$REMOTE_BASE/v3/processed_LF" "$REMOTE_BASE/data_transfer" \
        || { log "✗ cannot reach $REMOTE_HOST"; exit 1; }
fi

ERRORS=0
for pair in "${PAIRS[@]}"; do
    read -r LOCAL REMOTE <<< "$pair"
    if [ ! -d "$LOCAL" ]; then
        log "- $LOCAL: not found, skipped"
        continue
    fi
    log "--- $LOCAL -> $REMOTE ---"
    if rsync "${RSYNC_OPTS[@]}" -e "$SSH" "$LOCAL/" "$REMOTE_USER@$REMOTE_HOST:$REMOTE/" >> "$LOG" 2>&1; then
        log "✓ $LOCAL synced"
    else
        log "✗ $LOCAL sync FAILED (rsync exit $?)"
        ERRORS=$((ERRORS + 1))
    fi
done

if [ "$ERRORS" -eq 0 ]; then
    log "=== all syncs completed ==="
else
    log "=== sync finished with $ERRORS failure(s) ==="
    exit 1
fi

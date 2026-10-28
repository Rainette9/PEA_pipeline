#!/bin/bash
# EddyPro engine: run eddypro_rp + eddypro_fcc for a list of months and sensors.
# Called by run_monthly_eddypro.sh (cron) and run_bulk_eddypro.sh (manual), or directly:
#
#   MONTHS="202601 202602" bash run_eddypro_months.sh
#   HF_BASE=/data/disk1/shared/PEA/2025/processed_HF LF_BASE=/data/disk1/shared/PEA/2025/processed_LF \
#     MONTHS="202502 202503" SENSORS="LOWER UPPER" bash run_eddypro_months.sh
#
# Environment (all optional except MONTHS):
#   PEA_ROOT     data tree root, default /data/disk1/shared/PEA (scripts and engine live next to this file)
#   HF_BASE      processed_HF root (default $PEA_ROOT/processed_HF)
#   LF_BASE      processed_LF root for the biomet files (default $PEA_ROOT/processed_LF)
#   SENSORS      default "SFC LOWER UPPER BOTTOM"
#   TAG          project-id suffix, default v3_5min_biomet (output files: eddypro_PEA_<S>_<M>_<TAG>_*)
#   AVRG_LEN     flux averaging interval in minutes, default 5
#   MAX_LACK     max % of missing samples per averaging period, default 20 (v3)
#   ARCHIVE_DIR  if set, existing eddypro_*/processing_* files in the month's output dir are moved
#                to $ARCHIVE_DIR/<SENSOR>/<MONTH>/ before the run (never deleted)
#   PARALLEL     number of sensors processed concurrently, default 1
#   WORK_ROOT    per-job working directories (EddyPro writes fort.* and ../tmp relative to cwd),
#                default <transfer_scripts>/eddypro/work
#   LOG          log file, default $PEA_ROOT/data/eddypro_bulk.log
#
# Per sensor-month: biomet CSV built with make_biomet.py from the cleaned 1-min slow data
# (use_biom=2; use_biom=0 if no slow data), template PEA_<S>.eddypro adjusted (dates, paths,
# project_id, avrg_len, max_lack, full-day end times, no spectra/cospectra files), eddypro_rp,
# then eddypro_fcc on the fluxnet file of this very project id; after a successful fcc the
# rp full_output is removed so each month keeps exactly one full_output (the fcc one).
# Sensor-months without a processed_HF month folder are skipped.
#
# "v3" settings (reference since Oct 2026, same as the PC run 2025_v3_5min_biomet): avrg_len 5,
# max_lack 20, rot_meth 0 (Peddy double-rotates), detrend 0, tlag_meth 2, hf_meth 5, WPL,
# Burba on at SFC/LOWER/UPPER (BOTTOM is sonic-only), biomet TA/RH/PA from the 1-min slow data.

PEA_ROOT=${PEA_ROOT:-/data/disk1/shared/PEA}
TS=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
EDDYPRO_BIN=$TS/eddypro/eddypro-engine/bin/linux
EDDYPRO_ENGINE=$TS/eddypro/eddypro-engine/
SCRIPTS_DIR=$TS/eddypro/eddypro_scripts

HF_BASE=${HF_BASE:-$PEA_ROOT/processed_HF}
LF_BASE=${LF_BASE:-$PEA_ROOT/processed_LF}
SENSORS=${SENSORS:-"SFC LOWER UPPER BOTTOM"}
TAG=${TAG:-v3_5min_biomet}
AVRG_LEN=${AVRG_LEN:-5}
MAX_LACK=${MAX_LACK:-20}
PARALLEL=${PARALLEL:-1}
WORK_ROOT=${WORK_ROOT:-$TS/eddypro/work}
LOG=${LOG:-$PEA_ROOT/data/eddypro_bulk.log}

if [ -z "$MONTHS" ]; then
    echo "run_eddypro_months.sh: MONTHS is required (e.g. MONTHS=\"202601 202602\")" >&2
    exit 2
fi

log() { echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') $*" >> "$LOG"; }

run_job() {
    local sensor=$1 MONTH_STR=$2
    local YEAR=${MONTH_STR:0:4} MON=${MONTH_STR:4:2}
    local FIRST_DAY="${YEAR}-${MON}-01"
    local LAST_DAY
    LAST_DAY=$(date -d "${YEAR}-${MON}-01 +1 month -1 day" +%Y-%m-%d)
    local DATA_PATH="${HF_BASE}/${sensor}/${MONTH_STR}"
    local OUT_PATH="${HF_BASE}/${sensor}/Eddypro_output/${MONTH_STR}"
    local PROJECT_ID="PEA_${sensor}_${MONTH_STR}_${TAG}"
    local WORK="${WORK_ROOT}/${sensor}_${MONTH_STR}_${TAG}/run"
    local JOBLOG="${WORK}/../job.log"
    local TMP_FILE="${WORK}/${PROJECT_ID}.eddypro"

    if [ ! -d "$DATA_PATH" ]; then
        log "[$sensor $MONTH_STR] no processed_HF folder $DATA_PATH — skipped"
        return 0
    fi
    mkdir -p "$OUT_PATH" "$WORK"
    : > "$JOBLOG"
    log "[$sensor $MONTH_STR] start ($FIRST_DAY to $LAST_DAY), project $PROJECT_ID, log $JOBLOG"

    # Archive previous outputs of this month (rename, never delete)
    if [ -n "$ARCHIVE_DIR" ]; then
        local old
        old=$(find "$OUT_PATH" -maxdepth 1 \( -name 'eddypro_*' -o -name 'processing_*' \) 2>/dev/null)
        if [ -n "$old" ]; then
            mkdir -p "$ARCHIVE_DIR/$sensor/$MONTH_STR"
            echo "$old" | xargs -I{} mv {} "$ARCHIVE_DIR/$sensor/$MONTH_STR/"
            log "[$sensor $MONTH_STR] archived $(echo "$old" | wc -l) previous output entries to $ARCHIVE_DIR/$sensor/$MONTH_STR"
        fi
    fi

    # Biomet file from the cleaned 1-min slow data; run without biomet if none
    local BIOMET_FILE="${LF_BASE}/${sensor}/biomet/${sensor}_biomet_${MONTH_STR}.csv"
    local USE_BIOM
    if python3 "$TS/make_biomet.py" "$sensor" "$MONTH_STR" --base "$LF_BASE" --out "$BIOMET_FILE" >> "$JOBLOG" 2>&1; then
        USE_BIOM=2; log "[$sensor $MONTH_STR] biomet: $BIOMET_FILE"
    else
        USE_BIOM=0; BIOMET_FILE=""; log "[$sensor $MONTH_STR] biomet: none available — running without"
    fi

    sed \
        -e "s|^file_name=.*|file_name=${TMP_FILE}|" \
        -e "s|^project_id=.*|project_id=${PROJECT_ID}|" \
        -e "s|^proj_file=.*|proj_file=${SCRIPTS_DIR}/meta_PEA_${sensor}.metadata|" \
        -e "s|^data_path=.*|data_path=${DATA_PATH}|" \
        -e "s|^pr_subset=.*|pr_subset=1|" \
        -e "s|^pr_start_date=.*|pr_start_date=${FIRST_DAY}|" \
        -e "s|^pr_end_date=.*|pr_end_date=${LAST_DAY}|" \
        -e "s|^pr_start_time=.*|pr_start_time=00:00|" \
        -e "s|^pr_end_time=.*|pr_end_time=23:59|" \
        -e "s|^pf_start_date=.*|pf_start_date=${FIRST_DAY}|" \
        -e "s|^pf_end_date=.*|pf_end_date=${LAST_DAY}|" \
        -e "s|^pf_start_time=.*|pf_start_time=00:00|" \
        -e "s|^pf_end_time=.*|pf_end_time=23:59|" \
        -e "s|^to_start_date=.*|to_start_date=${FIRST_DAY}|" \
        -e "s|^to_end_date=.*|to_end_date=${LAST_DAY}|" \
        -e "s|^to_start_time=.*|to_start_time=00:00|" \
        -e "s|^to_end_time=.*|to_end_time=23:59|" \
        -e "s|^out_path=.*|out_path=${OUT_PATH}|" \
        -e "s|^avrg_len=.*|avrg_len=${AVRG_LEN}|" \
        -e "s|^max_lack=.*|max_lack=${MAX_LACK}|" \
        -e "s|^out_bin_sp=.*|out_bin_sp=0|" \
        -e "s|^out_bin_og=.*|out_bin_og=0|" \
        -e "s|^out_mean_spec=.*|out_mean_spec=0|" \
        -e "s|^out_mean_cosp=.*|out_mean_cosp=0|" \
        -e "s|^\(out_full_sp_[a-z0-9]*\)=.*|\1=0|" \
        -e "s|^\(out_full_cosp_w_[a-z0-9]*\)=.*|\1=0|" \
        -e "s|^use_biom=.*|use_biom=${USE_BIOM}|" \
        -e "s|^biom_file=.*|biom_file=${BIOMET_FILE}|" \
        -e "s|^ex_file=.*|ex_file=|" \
        -e "s|^sa_bin_spectra=.*|sa_bin_spectra=${OUT_PATH}/eddypro_binned_cospectra|" \
        -e "s|^sa_full_spectra=.*|sa_full_spectra=${OUT_PATH}/eddypro_full_cospectra|" \
        "${SCRIPTS_DIR}/PEA_${sensor}.eddypro" > "$TMP_FILE"

    if ! (cd "$WORK" && "$EDDYPRO_BIN/eddypro_rp" -s linux -e "$EDDYPRO_ENGINE" "$TMP_FILE" >> "$JOBLOG" 2>&1); then
        log "[$sensor $MONTH_STR] eddypro_rp FAILED — skipping fcc (see $JOBLOG)"
        return 1
    fi
    log "[$sensor $MONTH_STR] eddypro_rp done"

    local ESSENTIALS
    ESSENTIALS=$(find "$OUT_PATH" -maxdepth 1 -name "eddypro_${PROJECT_ID}_fluxnet_*.csv" | sort | tail -1)
    if [ -z "$ESSENTIALS" ]; then
        log "[$sensor $MONTH_STR] ERROR: no fluxnet file for $PROJECT_ID in $OUT_PATH — skipping fcc"
        return 1
    fi
    sed -i "s|^ex_file=.*|ex_file=${ESSENTIALS}|" "$TMP_FILE"

    if (cd "$WORK" && "$EDDYPRO_BIN/eddypro_fcc" -s linux -e "$EDDYPRO_ENGINE" "$TMP_FILE" >> "$JOBLOG" 2>&1); then
        # Keep one full_output per month: the fcc one (newest timestamp); drop the rp copy
        local fulls
        fulls=$(find "$OUT_PATH" -maxdepth 1 -name "eddypro_${PROJECT_ID}_full_output_*_adv.csv" | sort)
        if [ "$(echo "$fulls" | grep -c .)" -ge 2 ]; then
            echo "$fulls" | head -n -1 | xargs -r rm -f
            log "[$sensor $MONTH_STR] removed rp full_output, kept $(basename "$(echo "$fulls" | tail -1)")"
        fi
        log "[$sensor $MONTH_STR] eddypro_fcc done — OK"
    else
        log "[$sensor $MONTH_STR] eddypro_fcc FAILED (see $JOBLOG)"
        return 1
    fi
}

run_sensor_months() {
    local sensor=$1
    for M in $MONTHS; do
        run_job "$sensor" "$M"
    done
}

log "=== EddyPro run started: sensors [$SENSORS] months [$MONTHS] tag=$TAG avrg_len=$AVRG_LEN max_lack=$MAX_LACK HF_BASE=$HF_BASE parallel=$PARALLEL ==="
running=0
for sensor in $SENSORS; do
    if [ "$PARALLEL" -gt 1 ]; then
        run_sensor_months "$sensor" &
        running=$((running + 1))
        if [ "$running" -ge "$PARALLEL" ]; then
            wait -n 2>/dev/null || wait
            running=$((running - 1))
        fi
    else
        run_sensor_months "$sensor"
    fi
done
wait
log "=== EddyPro run complete ==="

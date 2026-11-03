# PEA pipeline

Automatic processing of the eddy-covariance and meteorological data from the Princess Elisabeth station,
Antarctica (PEA). Four measurement levels: `SFC` (surface station, ~2 m), `BOTTOM` (5 m sonic), `LOWER` (16.9 m)
and `UPPER` (25.4 m). The pipeline downloads the logger files from the station FTP every day, processes them
with Peddy (Julia), computes fluxes with EddyPro once a month, and copies the results to jed (EPFL SCITAS).

The current processing version is **v3** (see `docs/v3_consolidation_2026-10.md`).

## What runs when

The three cron jobs are listed in `crontab.txt`. All logs are in `$PEA_LOGS` (default `$PEA_ROOT/logs`).

| When | Script | What it does | Log |
|---|---|---|---|
| daily 02:03 | `run_daily_pipeline.sh` | 1. `datasync-snowflux-pea.py`: downloads new hourly files from the FTP and merges them into daily files under `data/<S>/<YYYYMM>/`. <br>2. Peddy for SFC, LOWER, UPPER, BOTTOM (`run_sensor.jl`, resume mode: only days not processed yet) → `processed_HF/` (10 Hz, hourly files) and `processed_LF/` (1-min slow data) | `pipeline.log`, `datasync.log` |
| 1st of month 10:00 | `run_eddypro.sh` | EddyPro for the previous month, all sensors: biomet file (`make_biomet.py`), project file from `eddypro/eddypro_scripts/`, `eddypro_rp` + `eddypro_fcc` → `processed_HF/<S>/Eddypro_output/<YYYYMM>/` | `eddypro.log` |
| every 10 days 06:00 | `sync_to_jed.sh` | rsync of `processed_HF`, `processed_LF` and the raw `data/<S>` to jed | `sync_jed.log` |

## Repository layout

```
pea_env.sh                 paths shared by all scripts (PEA_ROOT, PEA_LOGS, PEA_INPUT_BASE, PEA_HF_OUT, PEA_LF_OUT)
run_daily_pipeline.sh      cron: daily FTP sync + Peddy
run_eddypro.sh             cron: EddyPro for the previous month; MONTHS="202601 202602" for past months
sync_to_jed.sh             cron: copy to jed
datasync-snowflux-pea.py   FTP delta download + daily merge (called by run_daily_pipeline.sh); --backfill rebuilds missing daily files
make_biomet.py             EddyPro biomet file from the 1-min slow data (called by run_eddypro.sh)
crontab.txt                the three cron lines
DataProcessingScriptsJulia/  git submodule: the Julia driver around Peddy (tag v3.1); its Manifest.toml pins Peddy (fix_licor fe0c4c3)
eddypro/
  eddypro_scripts/         EddyPro project templates PEA_<S>.eddypro and metadata meta_PEA_<S>.metadata (v3 settings)
  eddypro-engine/          git submodule: LI-COR EddyPro 7.0.9 source, built locally (docs/SETUP_NEW_WORKSTATION.md, step 2a)
tools/                     manual tools, not run by cron
  rerun_peddy.sh             full Peddy reprocessing of one year into a separate *_rerun tree
  swap_in_rerun.sh           swap a finished rerun into place, archive the old output
  check_h2o.py               plausibility check of the processed H2O
  compare_hf.py              compare two sets of processed HF files
  compare_full_output.py     compare two EddyPro full_output files
docs/
  SETUP_NEW_WORKSTATION.md   how to install the pipeline on a new machine
  v3_consolidation_2026-10.md  definition of v3 and the October 2026 consolidation log
  rerun_h2o_2025_2026.md       log of the October 2026 H2O-reference rerun
```

`DataProcessingScriptsJulia/` is a submodule (https://github.com/Rainette9/DataProcessingScriptsJulia), pinned
to the commit tagged `v3.1` (same Peddy processing as `v3`; the SFC wind file is matched by the last date in the
OneMin name since the logger's clock reset of 2026-10-31). After pushing changes there, bump the pin here: check
out the new commit inside the submodule, then `git add DataProcessingScriptsJulia && git commit`. After
`git pull` on the workstation run `git submodule update` so the checkout follows the pin. The submodule is on a
detached HEAD: `git checkout main` inside it before committing there.

Not in this repository:
- **`.ftp_password`**: FTP password, mode 600, never committed.
- SSH key `~/.ssh/epfl` for jed.

## Data tree

The code lives wherever the repo is cloned (`transfer_scripts/` on the workstation); the data tree is
`PEA_ROOT` (default `/data/disk1/shared/PEA`, may be a network share). Every path below can be overridden
with the variables in `pea_env.sh`.

```
data/<S>/<YYYYMM>/          raw daily logger files (from the FTP); data/_raw/<S>/ the hourly originals; data/ftp_sync_state.json
processed_HF/<S>/<YYYYMM>/  Peddy output: <S>_Fastdata_proc_<date>_<HHMM>.dat, processing and H2O-reference logs
processed_HF/<S>/Eddypro_output/<YYYYMM>/   EddyPro output, file names eddypro_PEA_<S>_<YYYYMM>_v3_5min_biomet_*
processed_LF/<S>/<YYYYMM>/  1-min slow data <S>_OneMin_<date>.dat; biomet files in processed_LF/<S>/biomet/
2025/converted/<S>/         raw 2025 logger-card files (input for a 2025 rerun; its output goes into processed_HF/ and processed_LF/)
archive/                    output replaced by reruns (never deleted automatically)
logs/                       PEA_LOGS: cron logs and logs of manual reruns (put it on a local disk if PEA_ROOT is a share)
```

## Common tasks

```bash
cd $PEA_ROOT/transfer_scripts

# EddyPro for past months (e.g. after a rerun)
MONTHS="202601 202602" ARCHIVE_DIR=$PEA_ROOT/archive/eddypro_old nohup bash run_eddypro.sh &

# reprocess a whole year with Peddy, then swap it in
bash tools/rerun_peddy.sh 2026
PEA_INPUT_BASE=$PEA_ROOT/2025/converted bash tools/rerun_peddy.sh 2025 "SFC LOWER UPPER"   # 2025: logger-card raw
bash tools/swap_in_rerun.sh 2026

# rebuild daily raw files for days that only have hourly files (no FTP access)
python3 datasync-snowflux-pea.py --backfill

# check the processed H2O of one sensor
python3 tools/check_h2o.py summary $PEA_ROOT/processed_HF/UPPER
```

## Installation

See `docs/SETUP_NEW_WORKSTATION.md`. Short version: clone with `--recurse-submodules`, build the EddyPro engine
in `eddypro/eddypro-engine/prj` with `make`, run `Pkg.instantiate()` in `DataProcessingScriptsJulia`, put `.ftp_password` in place, install `crontab.txt`.

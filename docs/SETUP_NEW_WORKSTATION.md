# Setting up the PEA pipeline on a new workstation

Target: the new machine runs exactly what cryosAlp1008 runs today (FTP sync → Peddy v3 → EddyPro v3 →
rsync to jed) from the same scripts. Everything below assumes `PEA_ROOT=/data/.../PEA` on the new machine
(any path; all scripts source `pea_env.sh`, which reads `PEA_ROOT`, default `/data/disk1/shared/PEA`, and
`PEA_LOGS`, default `$PEA_ROOT/logs`). The code is cloned on the local disk; the data tree may be a network
share. If it is, set `PEA_LOGS` to a local folder (CIFS has no exec bits and is slow for appending logs).

## 1. Software
- Ubuntu 22.04/24.04, `rsync`, `python3` (3.10+; standard library only), `git`.
- Julia 1.11 or 1.12 (snap `julia` on the old machine; https://julialang.org/install). The Manifest was last
  resolved with 1.12.5; a different minor version rewrites `Manifest.toml` (versions of stdlib jlls only).
- `gfortran` and `make` (`sudo apt install gfortran make`) to build the EddyPro engine (step 2a).
- EddyPro 7 Linux engine: LI-COR's source is a git submodule of this repo, built in step 2a. The executables
  are not in git (LI-COR's repo ignores `bin/`).

## 2. Code
```
mkdir -p $PEA_ROOT && cd $PEA_ROOT
git clone --recurse-submodules https://github.com/Rainette9/PEA_pipeline.git transfer_scripts
#  -> pipeline scripts + submodules DataProcessingScriptsJulia (pinned to tag v3.1) and EddyPro engine source
#  -> then build the EddyPro engine (step 2a)
cd transfer_scripts/DataProcessingScriptsJulia
julia --project=. -e 'using Pkg; Pkg.Registry.update(); Pkg.instantiate(); Pkg.status("Peddy")'
#  -> Peddy v0.1.1 https://github.com/pleibers/Peddy.jl.git#fix_licor (tree d5815132 = commit fe0c4c3)
```
`DataProcessingScriptsJulia` is checked out at the commit this repo pins (detached HEAD). To update it later:
`git pull && git submodule update` in `transfer_scripts`. Before committing Julia changes on the workstation,
`git checkout main` inside the submodule.
A machine that already has `DataProcessingScriptsJulia/` as a separate plain clone (e.g. cryosAlp1008) keeps it:
`git pull && git submodule update --init` adopts the existing clone as the submodule and checks out the pinned
commit. Commit or stash local changes in it first.
Secrets and keys (never in git): `transfer_scripts/.ftp_password` (mode 600), `~/.ssh/epfl` (+ `.pub`) for
`engbers@jed.hpc.epfl.ch`, and `ssh-keyscan jed.hpc.epfl.ch >> ~/.ssh/known_hosts`.
Set the git identity: `git config user.name Rainette; git config user.email rainette.engbers@epfl.ch`.

## 2a. EddyPro engine (submodule, build from source)
`eddypro/eddypro-engine/` is a git submodule pointing at https://github.com/LI-COR-Environmental/eddypro-engine,
pinned to commit 3cabe63 ("Merge tag 'v7.0.9'"), the source of the engine used for the 2025 v3 run on the PC.
The scripts expect the executables in `eddypro/eddypro-engine/bin/linux/` and a writable `tmp/` next to them
(the engine writes scratch files there). After cloning this repo in step 2:
```
cd $PEA_ROOT/transfer_scripts
git submodule update --init          # not needed if you cloned with --recurse-submodules
cd eddypro/eddypro-engine/prj && make    # builds eddypro_rp and eddypro_fcc; run make from prj/, paths are relative
cd .. && mkdir -p tmp
ls -l bin/linux/                     # eddypro_rp (3,084,160 bytes) and eddypro_fcc (2,385,104 bytes)
ldd bin/linux/eddypro_rp | grep 'not found'   # no output = all libraries found
```
- `make` ends with `mv: cannot stat '*.mod'`. That message is harmless.
- Built with gfortran 13.3 (Ubuntu 24.04) this gives binaries byte-identical to the PC's v3 engine (checked
  2026-10-28). Another gfortran version can change results in the last digits; check with the March 2025
  equivalence sample (`v3_check_pc/`).
- Rebuild after a compiler or OS upgrade: `cd eddypro/eddypro-engine/prj && make clean_all && make`.
- Build products (`bin/`, `obj/`, `tmp/`) stay untracked; `.gitmodules` sets `ignore = untracked`, so they do not
  show up in `git status` of this repo.
- Moving an existing machine to the submodule: if `eddypro/eddypro-engine/` already exists as a plain copied folder,
  move it aside (`mv eddypro/eddypro-engine eddypro/eddypro-engine.old`) before `git pull` +
  `git submodule update --init`, then build as above and delete the old folder once a test month runs.
- Alternative without building: copy `eddypro/eddypro-engine/bin/linux/` from a working machine. The executables
  only need `libgfortran5` at run time.

## 3. Data (copy from the old workstation, same layout)
```
rsync -aH --info=progress2 cryos@128.178.60.219:/data/disk1/shared/PEA/data/            $PEA_ROOT/data/
rsync -aH cryos@128.178.60.219:/data/disk1/shared/PEA/processed_HF/  $PEA_ROOT/processed_HF/
rsync -aH cryos@128.178.60.219:/data/disk1/shared/PEA/processed_LF/  $PEA_ROOT/processed_LF/
rsync -aH cryos@128.178.60.219:/data/disk1/shared/PEA/2025/converted/ $PEA_ROOT/2025/converted/
mkdir -p $PEA_ROOT/logs $PEA_ROOT/archive
```
`data/ftp_sync_state.json` (inside `data/`) must come along, otherwise the FTP sync re-downloads the last 30 days.
Do the final `data/` + `processed_*` rsync after stopping the old cron (step 5), so nothing is missed.
`2025/converted/` is the raw input of the 2025 season (logger cards). Its output is reprocessed into the main
`processed_HF/` and `processed_LF/` trees with `PEA_INPUT_BASE=$PEA_ROOT/2025/converted bash tools/rerun_peddy.sh 2025`
followed by `tools/swap_in_rerun.sh 2025`; the old `2025/processed_*` trees on cryosAlp1008 are not needed.

## 4. Dry runs (in this order)
```
cd $PEA_ROOT/transfer_scripts
python3 datasync-snowflux-pea.py --dry-run                      # FTP reachable, state file found, nothing to do
PEA_HF_OUT=/tmp/pea_test PEA_LF_OUT=/tmp/pea_test julia --project=DataProcessingScriptsJulia \
    DataProcessingScriptsJulia/scripts/run_sensor.jl LOWER --restart --no-save-slow --from <yesterday> --to <yesterday>
                                                                 # 24 hourly files, log shows diag_margin=2, couple_sonic
MONTHS=<last month> SENSORS=BOTTOM HF_BASE=/tmp/pea_test_hf LF_BASE=/tmp/pea_test_lf bash run_eddypro.sh   # or a real month with ARCHIVE_DIR
rsync -n ... (see sync_to_jed.sh; run it once with `-n` added to the rsync line)
```

## 5. Cron (the three lines in `crontab.txt`; install with `crontab -e`)
```
PATH=/usr/local/bin:/usr/bin:/bin:<directory of julia>
3 2 * * *     $PEA_ROOT/transfer_scripts/run_daily_pipeline.sh
0 10 1 * *    $PEA_ROOT/transfer_scripts/run_eddypro.sh
0 6 */10 * *  $PEA_ROOT/transfer_scripts/sync_to_jed.sh >> $PEA_LOGS/sync_jed.log 2>&1
```
cron does not expand `$PEA_ROOT`, `$PEA_LOGS` or `~`: write the paths out, including the `julia` directory in
`PATH` (`dirname $(which julia)`). If `PEA_ROOT` or `PEA_LOGS` are not the defaults, put `PEA_ROOT=/path` and
`PEA_LOGS=/path` at the top of the crontab. On the old machine comment the three lines out (`crontab -e`) the
same day, so the two workstations never both write to jed.

## 6. Checks after the first days (all logs in `$PEA_LOGS`)
- `pipeline.log`: four `--- <S> done ---` lines; `datasync.log`: the new hourly files were downloaded.
- `processed_HF/<S>/<YYYYMM>/<S>_processing_log_<YYYYMM>.csv` grows by one block per day; `<S>_h2o_ref_*.csv` for LOWER/UPPER.
- First of the month: `eddypro.log` ends with `eddypro_fcc done — OK` for every sensor with data.
- `sync_jed.log`: all syncs `✓`.

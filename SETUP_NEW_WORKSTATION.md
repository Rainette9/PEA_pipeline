# Setting up the PEA pipeline on a new workstation

Target: the new machine runs exactly what cryosAlp1008 runs today (FTP sync → Peddy v3 → EddyPro v3 →
rsync to jed) from the same scripts. Everything below assumes `PEA_ROOT=/data/.../PEA` on the new machine
(any path; the scripts read `PEA_ROOT`, default `/data/disk1/shared/PEA`).

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
git clone --recurse-submodules https://github.com/Rainette9/PEA_pipeline.git transfer_scripts   # pipeline scripts + EddyPro engine source
#  -> then build the EddyPro engine (step 2a)
git clone https://github.com/Rainette9/DataProcessingScriptsJulia transfer_scripts/DataProcessingScriptsJulia
cd transfer_scripts/DataProcessingScriptsJulia && git checkout v3   # or main
julia --project=. -e 'using Pkg; Pkg.Registry.update(); Pkg.instantiate(); Pkg.status("Peddy")'
#  -> Peddy v0.1.1 https://github.com/pleibers/Peddy.jl.git#fix_licor (tree d5815132 = commit fe0c4c3)
```
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
rsync -aH cryos@128.178.60.219:/data/disk1/shared/PEA/2025/          $PEA_ROOT/2025/
mkdir -p $PEA_ROOT/logs $PEA_ROOT/archive
```
`data/ftp_sync_state.json` (inside `data/`) must come along, otherwise the FTP sync re-downloads the last 30 days.
Do the final `data/` + `processed_*` rsync after stopping the old cron (step 5), so nothing is missed.

## 4. Dry runs (in this order)
```
cd $PEA_ROOT/transfer_scripts
python3 datasync-snowflux-pea.py --dry-run                      # FTP reachable, state file found, nothing to do
PEA_HF_OUT=/tmp/pea_test PEA_LF_OUT=/tmp/pea_test julia --project=DataProcessingScriptsJulia \
    DataProcessingScriptsJulia/scripts/run_sensor.jl LOWER --restart --no-save-slow --from <yesterday> --to <yesterday>
                                                                 # 24 hourly files, log shows diag_margin=2, couple_sonic
MONTHS=<last month> SENSORS=BOTTOM HF_BASE=/tmp/pea_test_hf ... bash run_eddypro_months.sh   # or a real month with ARCHIVE_DIR
rsync -n ... (see sync_toscitas.sh; run it once with `-n` added to the rsync line)
```

## 5. Cron (same three lines as on the old machine; `crontab -e`)
```
3 2 * * *     $PEA_ROOT/transfer_scripts/run_daily_pipeline.sh
0 10 1 * *    $PEA_ROOT/transfer_scripts/run_monthly_eddypro.sh
0 6 */10 * *  $PEA_ROOT/transfer_scripts/sync_toscitas.sh >> $PEA_ROOT/transfer_scripts/sync.log 2>&1
```
If `PEA_ROOT` is not the default, put `PEA_ROOT=/path` at the top of the crontab. On the old machine comment the
three lines out (`crontab -e`) the same day, so the two workstations never both write to jed.

## 6. Checks after the first days
- `data/pipeline.log`: datasync downloaded the new hourly files; four `--- <S> done ---` lines.
- `processed_HF/<S>/<YYYYMM>/<S>_processing_log_<YYYYMM>.csv` grows by one block per day; `<S>_h2o_ref_*.csv` for LOWER/UPPER.
- First of the month: `data/eddypro_monthly.log` ends with `eddypro_fcc done — OK` for every sensor with data.
- `transfer_scripts/sync.log`: all syncs `✓`.

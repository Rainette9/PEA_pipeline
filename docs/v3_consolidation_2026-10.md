# Consolidation log: one PEA dataset, v3 settings, portable pipeline (started 2026-10-28)

Plan: `~/.claude/plans/partitioned-knitting-coral.md` (workstation). Background: `rerun_h2o_2025_2026.md` (Oct 1).

## Definition of v3
- Julia: `DataProcessingScriptsJulia` main at e24d8a6 (tag `v3`) = PC main 37a1226 (diag_margin, Ts median, couple_sonic,
  pres_offset, max_gap_samples, biomet writer, portable run_sensor) merged with the workstation branch Alp1008 184847e
  (H2O reference chain, env driver, -7999 masking). Peddy.jl `fix_licor` fe0c4c3 pinned (tree d5815132).
- EddyPro: avrg_len 5, max_lack 20, rot 0, detrend 0, tlag 2, hf 5, WPL, Burba (SFC/LOWER/UPPER), biomet, no spectra
  files, one full_output per month, project id `PEA_<S>_<YYYYMM>_v3_5min_biomet` (PC's 2025 run: `2025_v3_5min_biomet`).
- Biomet: SFC PA +80 kPa; LOWER TA/RH/PA own 16 m → UPPER 26 m → 10 m probe.

## Decisions (user, 2026-10-28)
Reprocess all sensors 2025+2026 with Peddy v3 here; workstation builds, rsyncs to jed; jed holds the scripts in git;
BOTTOM 2025 skipped; archives in `archive/` inside PEA; `/mnt/data1/PEA` verified then deleted; no Claude attribution in commits.

## Status log
- 10-28 16:10 UTC+1  Workstation branch committed (184847e), PC pushed 4e0f17b+37a1226, merge e24d8a6 made, smoke tests
  LOWER 2026-10-20 / SFC 2026-02-01 OK (24 files each, 0 failed; SFC P 81.4 kPa with offset). main = e24d8a6, tag v3.
  Push to GitHub pending: no credentials on the workstation; PC fetches over ssh (interactive) and pushes.
- 10-28 16:20  run_eddypro_months.sh + templates on v3 settings; make_biomet.py OFFSET/FALLBACK; PEA_ROOT in all scripts;
  rerun_peddy.sh / swap_in_rerun.sh generalised; transfer_scripts/.gitignore written (repo not yet created).
- 10-28 16:25  Folder cleanup: processed_*_archive_20261001, 2025 jed sample + pre-noref EddyPro archive, MRR_copy →
  `archive/`; empty *_rerun removed. /mnt/data1/PEA compared by name+size: only the root-level SFC Eddypro_output run
  (315 MB) and 7 small files were unique → `archive/mnt_data1_PEA_unique_20261028/`, then deleted.
- PC v3 sample for the equivalence check arriving in `v3_check_pc/` (2025/processed_HF/{SFC,UPPER}/202503 + EddyPro).

## Next
1. Push main + v3 (PC). 2. Equivalence check SFC/UPPER 202503 vs v3_check_pc. 3. `rerun_peddy.sh 2026`, then 2025
(SFC raw from jed first). 4. swap_in_rerun, EddyPro v3 2025+2026 with ARCHIVE_DIR=archive/eddypro_pre_v3.
5. sync_toscitas.sh → jed `DATA/MET/v3/...`; jed build_flux.py on v3 only; VERSION 0.11.0. 6. transfer_scripts git repo;
SETUP_NEW_WORKSTATION.md.
- 10-28 17:05  Equivalence check PASSED: UPPER 2025-03-10 processed here from 2025/converted with the merged code
  (main e24d8a6, Peddy fe0c4c3) is bit-identical to the PC's v3 output in v3_check_pc/ (24 files, 864000 rows,
  0 differing values, identical NaN pattern in Ux/Uy/Uz/Ts/H2O/P/diag_sonic/diag_gas; compare_hf.py).
- 10-28 17:35  Launched `rerun_peddy.sh 2026` (all sensors, 16 procs → processed_HF_rerun/) and
  `rerun_peddy.sh 2025 "LOWER UPPER"` (8 procs → 2025/processed_HF_rerun/). Logs: logs/peddy_<year>_<S>_*.log.
  SFC 2025 raw cards (20250208_SFC, 20251222_SFC, 20260121_SFC; ~28 GB; names TOA5_STN1fast_<N>.dat) being
  rsynced from jed into 2025/converted/ (jed inventory by the jed session; data_transfer has no 2025 months).
  jed note: processed_HF/2025/SFC/202511 on jed has only 86 hourly files (Nov 11–15) — the v3 rerun regenerates it.
- 10-28 17:45  SFC 2025 raw cards pulled from jed (3 folders, 28 GB, 6 min); `rerun_peddy.sh 2025 SFC` launched (4 procs).
  EddyPro equivalence run (my engine on the PC's UPPER 202503 v3 HF files) running; compare_full_output.py ready.
- 10-28 17:55  DataProcessingScriptsJulia main e24d8a6 + tag v3 pushed to GitHub from the PC (fast-forward). Workstation
  clone is on main, in sync. The PC user confirmed the H2O reference order (own → UPPER 26 m → 10 m; UPPER own → 10 m);
  differences vs the PC's 2025 v3 output are expected only where the 10 m probe now fills NaN minutes and for LOWER
  2025-12-27..31 (old driver forced UPPER for all of LOWER 2025).

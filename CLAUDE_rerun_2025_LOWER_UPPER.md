# CLAUDE.md: rerun 2025 LOWER/UPPER Peddy processing from raw data

This file provides guidance to Claude Code (claude.ai/code) for one task: reprocess the 2025 LOWER and UPPER eddy-covariance fast data with Peddy.jl from the raw logger files (`2025/converted`), with a correct LI-7500 H2O correction. Copy this file as `CLAUDE.md` into the working folder on the machine where `2025/converted` exists.

## Background (why this rerun is needed)

Station: Princess Elisabeth, Antarctica. Sensors: `LOWER` (sonic + LI-7500 at ~16.9 m, column suffix `_16m`) and `UPPER` (~26 m, suffix `_26m`). Driver repo: `DataProcessingScriptsJulia` (Peddy.jl from `../Peddy.jl`, branch `fix_licor`). Entry points `scripts/run_<H>.jl` → `src/process_sensor.jl::process_sensor`.

Peddy's `H2OCalibration` (`Peddy.jl/src/h2o_correction.jl`) corrects the LI-7500 H2O: per 1-min slow-data timestamp it replaces the LI minute-mean absorptance by a reference computed from slow TA and RH, keeping the high-frequency fluctuations. In the 2025 processing this went wrong:

- **UPPER**: corrected towards a reference RH 100× too small, so H2O ≈ 0 (often negative) instead of ~20–60 mmol m⁻³. Cause: the 2025 tower slow RH (`RH_26m_Avg`) is a 0–1 fraction. `build_lf_dimarray` divides RH by 100 and `correct_gas_analyzer!` multiplies by 100, so both expect percent from `clean_tower_slowdata`. The ×100 in `clean_tower_slowdata` was only added after 2025 was processed.
- **LOWER**: no usable 2025 slow data, so the correction was skipped (`has_slow` false per day). H2O stays at the raw LI-7500 level (~110–160 mmol m⁻³, implied RH 130–230 %).
- **UPPER 2025-12-31**: whole day H2O ≈ 32,600 mmol m⁻³, plus single 1e38 spikes (LOWER 2025-12-31 16:00). Cause not established. Check this day after the rerun.

The 2026 processing (current code) and SFC are fine.

## What the rerun must do

1. **UPPER**: process from raw with the current code (RH ×100 in `clean_tower_slowdata`).
2. **LOWER**: use the **UPPER probe's TA and RH together** as the H2O reference, i.e. transfer the absolute humidity from 25.4 m. Do not combine UPPER RH with LOWER temperature: the probe is ~2 K warmer in stable conditions, and vapour density varies much less with height than RH.
3. Mask slow-data logger zeros: rows with TA == 0 and RH == 0 exactly (8 such minutes in 2025 UPPER) must become missing. Otherwise the reference is RH 0 %.
4. After the pipeline, set H2O outside 0–400 mmol m⁻³ to NaN (saturation at +5 °C is ~380). This removes the 1e38 spikes.
5. Use `year = 2025` so `Peddy.default_calibration_coefficients(sensor, 2025)` picks the 2025 coefficients (LOWER A=4764.8, UPPER A=5502.41).

## Step 0: check the inputs

```bash
ls $ROOT/2025/converted            # expect visits like 20251226_LOWER, 20251226_UPPER, ...
```
Verify the RH scale in the raw UPPER slow files. `max(RH_26m_Avg)` must be ≤ 1 for the ×100 in `clean_tower_slowdata` to be right. If the raw files are already in percent, remove the ×100 for this run instead.

`$ROOT` is the folder that contains `2025/` (on the original machine `/home/engbers/Documents/PhD/EC_data_convert`). Several functions in `src/read_data,jl` have hard-coded default paths. Always pass `base_path` explicitly.

## Step 1: code changes in DataProcessingScriptsJulia

**a) H2O bounds after the pipeline.** In `src/process_sensor.jl`, right after `hf_result, _ = Peddy.get_results(output)`:

```julia
# Remove physically impossible H2O (mmol m-3) after the gas analyzer correction
vars = collect(dims(hf_result, Var))
ih = findfirst(==(:H2O), vars)
if ih !== nothing
    col = @view parent(hf_result)[:, ih]
    col[.!isnan.(col) .& ((col .< 0) .| (col .> 400))] .= NaN
end
```

**b) Logger zeros.** Add a helper (e.g. in `src/read_data,jl`) and call it on the cleaned slow data in both run scripts:

```julia
function mask_logger_zeros!(df::DataFrame, ta::String, rh::String)
    allowmissing!(df, [ta, rh])
    z = coalesce.((df[!, ta] .== 0) .& (df[!, rh] .== 0), false)
    df[z, ta] .= missing
    df[z, rh] .= missing
    println("  masked $(sum(z)) logger-zero rows")
    return df
end
```

**c) Optional, recommended: no far-away reference minutes.** `_find_nearest_lf_index` has no distance limit. On days where slow data covers only part of the day (2025-02-13, 2025-12-23 from 14:12, 2025-12-22), HF hours without slow data get corrected with a reference hours away. In `build_lf_dimarray`, put the day's slow data on a regular 1-min grid from `date - 1h` to `date + 1d + 1h`, with NaN where data are missing. Optionally interpolate gaps ≤ 10 min. NaN reference then gives NaN H2O for those samples. `scripts/fix_h2o_2025.jl::reference_for_day` (see below) does exactly this and can be copied.

**d) New run scripts** `scripts/run_UPPER_2025.jl` and `scripts/run_LOWER_2025.jl`. Write output to a **separate folder** (`processed_HF_rerun`) so the existing files stay available for comparison. This also avoids `resume` skipping dates that already have output.

```julia
# run_UPPER_2025.jl (same includes/usings as scripts/run_UPPER.jl)
input_base       = "$ROOT/2025/converted"
processed_output = "$ROOT/2025/processed_HF_rerun"
slow_output      = "$ROOT/2025/processed_slow_rerun/UPPER"
year             = 2025

slow_raw = read_slow_data(base_path=input_base, sensor="UPPER")
unique!(slow_raw, :TIMESTAMP); sort!(slow_raw, :TIMESTAMP)
slow_data = clean_tower_slowdata(slow_raw, "_26m")
mask_logger_zeros!(slow_data, "Temp_26m_Avg", "RH_26m_Avg")
save_slow_data(slow_data, slow_output, "UPPER")

process_sensor(input_base=input_base, sensor="UPPER", processed_output=processed_output,
               year=year, resume=!("--restart" in ARGS), slow_data=slow_data)
```

```julia
# run_LOWER_2025.jl: reference = UPPER probe (TA and RH), renamed to the LOWER column names
input_base       = "$ROOT/2025/converted"
processed_output = "$ROOT/2025/processed_HF_rerun"
year             = 2025

slow_raw = read_slow_data(base_path=input_base, sensor="UPPER")
unique!(slow_raw, :TIMESTAMP); sort!(slow_raw, :TIMESTAMP)
up = clean_tower_slowdata(slow_raw, "_26m")
mask_logger_zeros!(up, "Temp_26m_Avg", "RH_26m_Avg")
slow_data = select(up, :TIMESTAMP, :Temp_26m_Avg => :Temp_16m_Avg, :RH_26m_Avg => :RH_16m_Avg)
# Do not save this as LOWER slow data: it is the UPPER probe.

process_sensor(input_base=input_base, sensor="LOWER", processed_output=processed_output,
               year=year, resume=!("--restart" in ARGS), slow_data=slow_data)
```

Do not write biomet files from these scripts. The EddyPro biomet inputs (`2025/biomet/<H>/`) come from `2026/eddypro/eddypro_scripts/make_biomet_2025.py` and stay as they are. That script handles RH in fraction or percent.

## Step 2: run

```bash
cd DataProcessingScriptsJulia
julia --project=. scripts/run_UPPER_2025.jl > upper_2025.log 2>&1 &
julia --project=. scripts/run_LOWER_2025.jl > lower_2025.log 2>&1 &
```
Julia buffers stdout when redirected. Follow progress by counting files in `2025/processed_HF_rerun/<H>/2025*/`. Expected days with fast data: LOWER 2025-02-11 … 06-30 and 12-22 … 12-31 (~149 days); UPPER 2025-02-14 … 06-30 and 12-22 … 12-31 (~147 days).

## Step 3: verify before using the data

1. **Correction actually ran.** In `<H>_processing_log_YYYYMM.csv`, `gas_analyzer,runtime` rows should take seconds, not ~1e-7 s (that means skipped). Count per month: nearly all days should have run, for LOWER too.
2. **Plausible H2O.** Per hour: mean H2O and mean Ts → implied RH = 100 · e / e_s(Ts), with e = H2O/1000 · 8.314 · (Ts + 273.15) and e_s = 611.2 · exp(17.67 Ts / (Ts + 243.5)). Medians should be ~30–60 % and follow the probe RH. Before the fix they were ~0.5 % (UPPER) and 130–230 % (LOWER). No negative values, nothing above 400.
3. **2025-12-31 UPPER** is plausible (expected ~50–70 mmol m⁻³), and the 1e38 spikes are gone.
4. **Compare with the fixed files**, if `2025/processed_HF` from the original machine is available. Those were made with `scripts/fix_h2o_2025.jl`, which re-applies Peddy's correction on the processed files with the same UPPER reference. Within-minute H2O fluctuations should correlate > 0.95, and hourly mean H2O should agree within a few tenths of a mmol m⁻³. Larger differences point to the despiking or gap-filling order, or to partial-day reference coverage (Step 1c).

## Step 4: swap in and rerun EddyPro (on the machine with the EddyPro setup)

1. Back up or replace the fast files: move `2025/processed_HF/<H>/2025*/` aside and put the `processed_HF_rerun/<H>/2025*/` folders in their place. Keep `2025/processed_HF/<H>/Eddypro_output/` where it is.
2. Delete outdated EddyPro 5-min outputs for LOWER/UPPER, if any: `find 2025/processed_HF/{LOWER,UPPER}/Eddypro_output -name '*2025_5min_biomet*' -delete`, and `rm -rf 2026/eddypro/tmp/{LOWER,UPPER}_2025_5min_biomet` (the run logs append).
3. Run, each height from its own directory (Fortran `fort.*` scratch files are written to the current working directory):
   ```bash
   EP=$ROOT/2026/eddypro
   mkdir -p $EP/tmp/LOWER_2025_5min_biomet $EP/tmp/UPPER_2025_5min_biomet
   (cd $EP/tmp/LOWER_2025_5min_biomet && $EP/run_2025_5min_biomet.sh LOWER)
   (cd $EP/tmp/UPPER_2025_5min_biomet && $EP/run_2025_5min_biomet.sh UPPER)
   ```
   Each run ends with `All months complete for <H>` in `tmp/<H>_2025_5min_biomet/logs/all.log`. Outputs: `2025/processed_HF/<H>/Eddypro_output/YYYYMM/eddypro_2025_5min_biomet_*`. The 3-min biomet runs (`run_2025_3min_biomet.sh`) used the broken H2O as well and need the same rerun if they are still used.
4. MRD (`scripts/run_mrd.jl`) reads the processed fast data. Rerun it for LOWER/UPPER 2025 if MRD results involving H2O are used.

## Known limitation of Peddy's H2O correction

Each minute's mean H2O is set to the probe-derived value, so H2O variability slower than ~1 min follows the slow RH/TA probe, including its 0.01 °C / 0.001 RH resolution steps, not the LI-7500. For 3–5 min flux averaging this can damp the low-frequency part of LE. This applies to all heights and years processed with `H2OCalibration`, SFC included.

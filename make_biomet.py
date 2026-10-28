#!/usr/bin/env python3
"""
Build an EddyPro biomet file for one sensor and one month from the cleaned
one-minute slow data written by the Julia pipeline (processed_LF).

Usage:
    python3 make_biomet.py SENSOR YYYYMM [--base PROCESSED_LF_DIR] [--out PATH]

Reads   {base}/{SENSOR}/{YYYYMM}/{SENSOR}_OneMin_*.dat  (TOA5, 4 header rows)
Writes  {base}/{SENSOR}/biomet/{SENSOR}_biomet_{YYYYMM}.csv
        (base defaults to /data/disk1/shared/PEA/processed_LF; pass --base for the 2025 tree)

Cleaning: logger codes (-7999) and -9999 become -9999; TA outside [-80, 30] C,
RH outside [0, 105] %, PA outside [50, 110] kPa become -9999. RH written as 0-1
fractions by older Julia runs (max <= 1.5 over the month) is multiplied by 100.
Offsets (OFFSET): the SFC logger stores the LI-7500 pressure as kPa - 80, so
80 kPa is added before the bounds check (same as pres_offset in the Julia
SENSORS table).
Fallback (FALLBACK): for LOWER, minutes where the own 16 m probe has no value
are filled from the UPPER 26 m probe, then from the 10 m probe on the LOWER
logger (same order as the Julia H2O reference chain; the 10 m probe has TA/RH
only); the share of fallback minutes per column and source is printed.

Output is EddyPro "native header" biomet format:
    row 1: variable names  (TIMESTAMP_1, TA_1_1_1, RH_1_1_1, PA_1_1_1, SW_IN_1_1_1, ...)
    row 2: units           (timestamp column carries the format string)
    rows : data, no quotes, -9999 for missing

Timestamps are kept as written by the logger / Julia (end of the 1-min
averaging interval), matching biom_tstamp_ref=end in the .eddypro templates.

IMPORTANT: EddyPro picks which biomet column feeds the flux calculation via
the 1-based column indices biom_ta / biom_rh / biom_pa / biom_rg / biom_lwin
in the .eddypro templates (TIMESTAMP_1 counts as column 1). The column order
in COLUMN_MAP below must therefore stay in sync with those template values:
    SFC/LOWER/UPPER: biom_ta=2 biom_rh=3 biom_pa=4 biom_rg=5 biom_lwin=7
    BOTTOM:          biom_ta=2 biom_rh=3 biom_pa=0 biom_rg=4 biom_lwin=0
The templates also need use_biom=2 (external biomet file).

Exit status 0 on success, 1 if no input files were found (so callers can
fall back to running EddyPro without biomet).
"""

import argparse
import csv
import math
import os
import sys

BASE = os.path.join(os.environ.get("PEA_ROOT", "/data/disk1/shared/PEA"), "processed_LF")
NODATA = "-9999"

# Plausibility bounds per EddyPro label (values outside -> -9999)
BOUNDS = {
    "TA_1_1_1": (-80.0, 30.0),
    "RH_1_1_1": (0.0, 105.0),
    "PA_1_1_1": (50.0, 110.0),
}

# EddyPro label -> (source column in the OneMin file, EddyPro unit string)
COLUMN_MAP = {
    "SFC": {
        "TA_1_1_1":     ("TA",            "C"),
        "RH_1_1_1":     ("RH",            "%"),
        "PA_1_1_1":     ("LI_Pres_Avg",   "kPa"),
        "SW_IN_1_1_1":  ("SWdown1",       "W+1m-2"),
        "SW_OUT_1_1_1": ("SWup1",         "W+1m-2"),
        "LW_IN_1_1_1":  ("LWdown1",       "W+1m-2"),
        "LW_OUT_1_1_1": ("LWup1",         "W+1m-2"),
    },
    "LOWER": {
        "TA_1_1_1":     ("Temp_16m_Avg",         "C"),
        "RH_1_1_1":     ("RH_16m_Avg",           "%"),
        "PA_1_1_1":     ("AP_16m_Avg",           "kPa"),
        "SW_IN_1_1_1":  ("Incoming_SW_16m_Avg",  "W+1m-2"),
        "SW_OUT_1_1_1": ("Outgoing_SW_16m_Avg",  "W+1m-2"),
        "LW_IN_1_1_1":  ("Incoming_LW_16m_Avg",  "W+1m-2"),
        "LW_OUT_1_1_1": ("Outgoing_LW_16m_Avg",  "W+1m-2"),
    },
    "UPPER": {
        "TA_1_1_1":     ("Temp_26m_Avg",         "C"),
        "RH_1_1_1":     ("RH_26m_Avg",           "%"),
        "PA_1_1_1":     ("AP_26m_Avg",           "kPa"),
        "SW_IN_1_1_1":  ("Incoming_SW_26m_Avg",  "W+1m-2"),
        "SW_OUT_1_1_1": ("Outgoing_SW_26m_Avg",  "W+1m-2"),
        "LW_IN_1_1_1":  ("Incoming_LW_26m_Avg",  "W+1m-2"),
        "LW_OUT_1_1_1": ("Outgoing_LW_26m_Avg",  "W+1m-2"),
    },
    "BOTTOM": {
        "TA_1_1_1":     ("Temp_5m_Avg",  "C"),
        "RH_1_1_1":     ("RH_5m_Avg",    "%"),
        "SW_IN_1_1_1":  ("SWdn_5m",      "W+1m-2"),
    },
}


# (sensor, label) -> value added before the bounds check
OFFSET = {
    ("SFC", "PA_1_1_1"): 80.0,
}

# sensor -> ordered list of (fallback sensor, {label: source column in that sensor's OneMin files})
FALLBACK = {
    "LOWER": [
        ("UPPER", {
            "TA_1_1_1":     "Temp_26m_Avg",
            "RH_1_1_1":     "RH_26m_Avg",
            "PA_1_1_1":     "AP_26m_Avg",
            "SW_IN_1_1_1":  "Incoming_SW_26m_Avg",
            "SW_OUT_1_1_1": "Outgoing_SW_26m_Avg",
            "LW_IN_1_1_1":  "Incoming_LW_26m_Avg",
            "LW_OUT_1_1_1": "Outgoing_LW_26m_Avg",
        }),
        ("LOWER", {                      # 10 m probe on the LOWER logger
            "TA_1_1_1":     "Temp_10m_Avg",
            "RH_1_1_1":     "RH_10m_Avg",
        }),
    ],
}


def parse_value(raw: str):
    """Parse one data cell: None for missing/NaN/logger codes (<= -7000), else float."""
    s = raw.strip().strip('"')
    if s == "" or s.upper() in ("NAN", "NA"):
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if math.isnan(v) or math.isinf(v) or v <= -7000:
        return None
    return v


def read_onemin(in_dir, files, src_map):
    """Read OneMin TOA5 files; return ([(ts_out, {label: value|None})], set of missing source columns)."""
    records = []
    n_missing_col = set()
    for fname in files:
        with open(os.path.join(in_dir, fname), newline="") as fi:
            rows = list(csv.reader(fi))
        if len(rows) < 5:
            continue
        header = rows[1]
        idx = {}
        for label, src in src_map.items():
            if src in header:
                idx[label] = header.index(src)
            else:
                n_missing_col.add(src)
        for row in rows[4:]:
            if not row:
                continue
            ts = row[0].strip('"')          # "YYYY-MM-DD HH:MM:SS"
            if len(ts) < 16:
                continue
            ts_out = ts[:10] + " " + ts[11:13] + ts[14:16]
            vals = {l: (parse_value(row[idx[l]]) if l in idx and idx[l] < len(row) else None)
                    for l in src_map}
            records.append((ts_out, vals))
    return records, n_missing_col


def fmt_value(v) -> str:
    """Format a parsed value for the biomet file."""
    if v is None:
        return NODATA
    return f"{v:.6g}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sensor", choices=sorted(COLUMN_MAP))
    ap.add_argument("month", help="YYYYMM")
    ap.add_argument("--base", default=BASE, help=f"processed_LF root (default {BASE})")
    ap.add_argument("--out", help="output CSV path (default: {base}/SENSOR/biomet/...)")
    args = ap.parse_args()
    base = args.base

    sensor, month = args.sensor, args.month
    if len(month) != 6 or not month.isdigit():
        ap.error("month must be YYYYMM")

    in_dir = os.path.join(base, sensor, month)
    files = sorted(f for f in os.listdir(in_dir)
                   if f.startswith(f"{sensor}_OneMin_") and f.endswith(".dat")) \
        if os.path.isdir(in_dir) else []
    if not files:
        print(f"make_biomet: no OneMin files in {in_dir}", file=sys.stderr)
        return 1

    out_path = args.out or os.path.join(base, sensor, "biomet", f"{sensor}_biomet_{month}.csv")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    mapping = COLUMN_MAP[sensor]
    labels = ["TIMESTAMP_1"] + list(mapping)
    units = ["yyyy-mm-dd HHMM"] + [u for _, u in mapping.values()]

    # Pass 1: read and parse all rows of the month
    records, n_missing_col = read_onemin(in_dir, files, {l: src for l, (src, _) in mapping.items()})

    # RH scale: older Julia runs wrote RH as a 0-1 fraction
    rh_vals = [v["RH_1_1_1"] for _, v in records if v.get("RH_1_1_1") is not None]
    if rh_vals and max(rh_vals) <= 1.5:
        for _, v in records:
            if v.get("RH_1_1_1") is not None:
                v["RH_1_1_1"] *= 100.0
        print(f"make_biomet: {sensor} {month}: RH_1_1_1 was a 0-1 fraction (max {max(rh_vals):.3f}) -> x100")

    # Offsets, then plausibility bounds
    for _, v in records:
        for label in mapping:
            off = OFFSET.get((sensor, label))
            if off and v.get(label) is not None:
                v[label] += off
        for label, (lo, hi) in BOUNDS.items():
            x = v.get(label)
            if x is not None and not (lo <= x <= hi):
                v[label] = None

    # Fallback sources, in order, for minutes without an own value
    for fb_sensor, fb_map in FALLBACK.get(sensor, []):
        fb_dir = os.path.join(base, fb_sensor, month)
        fb_files = sorted(f for f in os.listdir(fb_dir)
                          if f.startswith(f"{fb_sensor}_OneMin_") and f.endswith(".dat")) \
            if os.path.isdir(fb_dir) else []
        if fb_files:
            fb_records, _ = read_onemin(fb_dir, fb_files, fb_map)
            fb = {ts: v for ts, v in fb_records}
            fb_rh = [v["RH_1_1_1"] for v in fb.values() if v.get("RH_1_1_1") is not None]
            if fb_rh and max(fb_rh) <= 1.5:
                for v in fb.values():
                    if v.get("RH_1_1_1") is not None:
                        v["RH_1_1_1"] *= 100.0
            filled = {l: 0 for l in fb_map}
            for ts, v in records:
                f = fb.get(ts)
                if f is None:
                    continue
                for label in fb_map:
                    if v.get(label) is None and f.get(label) is not None:
                        x = f[label]
                        lo, hi = BOUNDS.get(label, (-math.inf, math.inf))
                        if lo <= x <= hi:
                            v[label] = x
                            filled[label] += 1
            n = max(len(records), 1)
            share = " ".join(f"{l.split('_')[0]}={100*filled[l]/n:.0f}%" for l in fb_map)
            print(f"make_biomet: {sensor} {month}: filled from {fb_sensor} ({'/'.join(fb_map.values())[:40]}...): {share}")
        else:
            print(f"make_biomet: {sensor} {month}: no {fb_sensor} OneMin files for fallback")

    # Pass 2: write
    n_rows = 0
    valid = {l: 0 for l in mapping}
    with open(out_path, "w", newline="") as fo:
        w = csv.writer(fo, lineterminator="\n")
        w.writerow(labels)
        w.writerow(units)
        for ts_out, v in records:
            w.writerow([ts_out] + [fmt_value(v[l]) for l in mapping])
            n_rows += 1
            for l in mapping:
                if v[l] is not None:
                    valid[l] += 1
    if n_rows:
        share = " ".join(f"{l.split('_')[0]}={100*valid[l]/n_rows:.0f}%" for l in mapping)
        print(f"make_biomet: {sensor} {month}: valid share {share}")

    if n_missing_col:
        print(f"make_biomet: WARNING columns not found in {sensor} OneMin files: "
              f"{sorted(n_missing_col)} (written as {NODATA})", file=sys.stderr)
    print(f"make_biomet: {sensor} {month}: {n_rows} records from {len(files)} files -> {out_path}")
    return 0 if n_rows > 0 else 1


if __name__ == "__main__":
    sys.exit(main())

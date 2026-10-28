#!/usr/bin/env python3
"""
Shift LOWER processed timestamps by -1 hour.

Window: [2026-03-29 23:00, 2026-06-30 10:00)  (inclusive start, exclusive end)
Shift:  -1 hour

Applies to:
  processed_HF/LOWER/YYYYMM/LOWER_Fastdata_proc_YYYY-MM-DD_HHMM.dat
  processed_LF/LOWER/YYYYMM/LOWER_OneMin_YYYY-MM-DD.dat

Both filenames and internal TIMESTAMP values are corrected.

Usage:
  python3 shift_lower_timestamps.py              # run on all affected files
  python3 shift_lower_timestamps.py --test       # process only 2 HF + 2 LF files
  python3 shift_lower_timestamps.py --dry-run    # show what would change, touch nothing
"""

import os, re, sys, tempfile, argparse
from datetime import datetime, timedelta
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

HF_BASE = Path("/data/disk1/shared/PEA/processed_HF/LOWER")
LF_BASE = Path("/data/disk1/shared/PEA/processed_LF/LOWER")

SHIFT_START = datetime(2026, 3, 29, 23, 0, 0)   # inclusive
SHIFT_END   = datetime(2026, 6, 30, 10, 0, 0)   # exclusive
SHIFT       = timedelta(hours=-1)

# ── Filename patterns ──────────────────────────────────────────────────────────

# LOWER_Fastdata_proc_2026-03-29_2300.dat
HF_RE = re.compile(r"^LOWER_Fastdata_proc_(\d{4}-\d{2}-\d{2})_(\d{4})\.dat$")
# LOWER_OneMin_2026-03-29.dat
LF_RE = re.compile(r"^LOWER_OneMin_(\d{4}-\d{2}-\d{2})\.dat$")

# LF (TOA5) quoted timestamp:  "2026-03-29 00:00:00",...
LF_TS_RE = re.compile(r'^"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)"')

# HF (ICSV) unquoted timestamp with T-separator:  2026-03-29T23:00:00.0,...
HF_TS_RE = re.compile(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)')

# ── Helpers ────────────────────────────────────────────────────────────────────

def parse_hf_dt(date_str: str, hhmm: str) -> datetime:
    h, m = int(hhmm[:2]), int(hhmm[2:])
    return datetime.strptime(date_str, "%Y-%m-%d").replace(hour=h, minute=m)

def hf_components(dt: datetime):
    """Return (yyyymm, filename) for an HF file whose hour starts at dt."""
    yyyymm = dt.strftime("%Y%m")
    fname  = f"LOWER_Fastdata_proc_{dt.strftime('%Y-%m-%d_%H%M')}.dat"
    return yyyymm, fname

def lf_components(date_str: str):
    """Return (yyyymm, filename) for an LF daily file."""
    yyyymm = date_str.replace("-", "")[:6]
    fname  = f"LOWER_OneMin_{date_str}.dat"
    return yyyymm, fname

def in_window(dt: datetime) -> bool:
    return SHIFT_START <= dt < SHIFT_END

def shift_content_hf(text: str) -> str:
    """
    Shift every timestamp in an ICSV HF file by SHIFT.
    Line 1 is the column-name header (kept verbatim).
    Data lines: YYYY-MM-DDTHH:MM:SS.f,Ux,Uy,...
    """
    lines = text.splitlines(keepends=True)
    out = lines[:1]   # keep column-name header unchanged
    for line in lines[1:]:
        m = HF_TS_RE.match(line)
        if m:
            dt  = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")
            frac = m.group(2)                              # e.g. ".0"
            new_ts = (dt + SHIFT).strftime("%Y-%m-%dT%H:%M:%S") + frac
            out.append(new_ts + line[m.end():])
        else:
            out.append(line)
    return "".join(out)

def write_atomic(path: Path, text: str):
    """Write text to path atomically (temp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

# ── HF processing ─────────────────────────────────────────────────────────────

def process_hf(dry_run=False, test_limit=None):
    print("\n=== HF files ===")
    count = 0
    errors = 0

    # Collect all HF .dat files, sorted chronologically
    candidates = []
    for month_dir in sorted(HF_BASE.iterdir()):
        if not month_dir.is_dir():
            continue
        for f in sorted(month_dir.iterdir()):
            m = HF_RE.match(f.name)
            if not m:
                continue
            dt = parse_hf_dt(m.group(1), m.group(2))
            if in_window(dt):
                candidates.append((dt, f))

    if test_limit:
        candidates = candidates[:test_limit]

    for dt, src_path in candidates:
        new_dt = dt + SHIFT
        new_yyyymm, new_fname = hf_components(new_dt)
        dst_path = HF_BASE / new_yyyymm / new_fname

        overwriting = dst_path.exists() and dst_path != src_path
        tag = "  (overwrites existing)" if overwriting else ""
        print(f"  {src_path.parent.name}/{src_path.name}")
        print(f"    → {new_yyyymm}/{new_fname}{tag}")

        if dry_run:
            count += 1
            continue

        try:
            text = src_path.read_text(encoding="utf-8")
            shifted = shift_content_hf(text)
            write_atomic(dst_path, shifted)
            if dst_path != src_path:
                src_path.unlink()
            count += 1
        except Exception as e:
            print(f"    ERROR: {e}")
            errors += 1

    print(f"\nHF: {count} file(s) shifted, {errors} error(s)/skipped.")
    return errors

# ── LF processing ─────────────────────────────────────────────────────────────

def process_lf(dry_run=False, test_limit=None):
    """
    Batch approach: read all affected LF files, shift timestamps in window,
    regroup by date, write new daily files.  Handles day-boundary crossings
    (e.g. March 30 00:xx → March 29 23:xx) automatically.
    """
    print("\n=== LF files ===")

    # Date range to load: one day before SHIFT_START through SHIFT_END date
    from datetime import date as date_type
    load_start = (SHIFT_START + SHIFT).date()   # one day might shift into here
    load_end   = SHIFT_END.date()               # include June 30

    # Collect paths for all LF files in [load_start, load_end]
    lf_files = {}   # date_str → Path
    for month_dir in sorted(LF_BASE.iterdir()):
        if not month_dir.is_dir():
            continue
        for f in sorted(month_dir.iterdir()):
            m = LF_RE.match(f.name)
            if not m:
                continue
            d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            if load_start <= d <= load_end:
                lf_files[m.group(1)] = f

    if not lf_files:
        print("  No LF files found in range.")
        return 0

    print(f"  Loading {len(lf_files)} LF file(s)...")

    if test_limit:
        items = list(sorted(lf_files.items()))[:test_limit]
        lf_files = dict(items)
        print(f"  (test mode: limiting to {len(lf_files)} file(s))")

    # Read all rows, tracking which came from which file
    all_rows = []        # list of (datetime, list_of_field_strings)
    header_template = None   # (rows 1-4) from first file read

    for date_str, path in sorted(lf_files.items()):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception as e:
            print(f"  ERROR reading {path.name}: {e}")
            continue

        if header_template is None and len(lines) >= 4:
            header_template = lines[:4]

        for line in lines[4:]:
            if not line.strip():
                continue
            # Skip embedded re-header blocks (start with "TOA5")
            if line.startswith('"TOA5"'):
                continue
            m = LF_TS_RE.match(line)
            if not m:
                continue
            ts_str = m.group(1)
            try:
                dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            rest = line[m.end():]   # everything after the timestamp field
            all_rows.append((dt, rest))

    if not all_rows:
        print("  No data rows found.")
        return 0

    # Shift timestamps in window
    shifted_rows = []
    for dt, rest in all_rows:
        new_dt = (dt + SHIFT) if in_window(dt) else dt
        shifted_rows.append((new_dt, rest))

    # Regroup by date
    by_date = {}
    for dt, rest in shifted_rows:
        key = dt.strftime("%Y-%m-%d")
        by_date.setdefault(key, []).append((dt, rest))

    # Write new files
    count = 0
    errors = 0
    for date_str in sorted(by_date):
        yyyymm, fname = lf_components(date_str)
        dst_path = LF_BASE / yyyymm / fname

        rows = sorted(by_date[date_str], key=lambda x: x[0])
        print(f"  {yyyymm}/{fname}  ({len(rows)} rows)")

        if dry_run:
            count += 1
            continue

        try:
            lines_out = list(header_template) if header_template else []
            for dt, rest in rows:
                ts_out = dt.strftime("%Y-%m-%d %H:%M:%S")
                lines_out.append(f'"{ts_out}"{rest}')
            text = "\n".join(lines_out) + "\n"
            write_atomic(dst_path, text)
            count += 1
        except Exception as e:
            print(f"    ERROR: {e}")
            errors += 1

    # Remove LF files that no longer have any data after regrouping
    # (e.g. a file whose all rows shifted into another date)
    regrouped_dates = set(by_date.keys())
    for date_str, path in lf_files.items():
        if date_str not in regrouped_dates:
            print(f"  Removing {path.name} (all rows shifted out)")
            if not dry_run:
                path.unlink()

    print(f"\nLF: {count} file(s) written, {errors} error(s).")
    return errors

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would change without writing anything")
    ap.add_argument("--test", action="store_true",
                    help="Process only the first 2 HF files and 2 LF files")
    args = ap.parse_args()

    dry_run    = args.dry_run
    test_limit = 2 if args.test else None

    print(f"Shift window : {SHIFT_START} → {SHIFT_END}  (exclusive end)")
    print(f"Shift amount : {SHIFT}")
    print(f"Mode         : {'DRY RUN' if dry_run else ('TEST (2 files each)' if test_limit else 'FULL RUN')}")

    errs = process_hf(dry_run=dry_run, test_limit=test_limit)
    errs += process_lf(dry_run=dry_run, test_limit=test_limit)

    if errs:
        print(f"\n{errs} total error(s) — review output above.")
        sys.exit(1)
    else:
        print("\nDone.")

if __name__ == "__main__":
    main()

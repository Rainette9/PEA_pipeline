#!/usr/bin/env python3
"""
Backfill missing daily files for all sensors from existing raw hourly files.
Rebuilds any date where raw hourly files exist but no daily file has been written.
"""

import os
import re
import sys
import tempfile
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

LOCAL_BASE = os.path.join(os.environ.get("PEA_ROOT", "/data/disk1/shared/PEA"), "data")
RAW_SUBDIR = "_raw"
SENSORS = ["SFC", "BOTTOM", "LOWER", "UPPER"]
TOA5_HEADER_LINES = 4

HOURLY_RE = re.compile(
    r"^(?P<prefix>.+?)(?P<Y>\d{4})_(?P<M>\d{2})_(?P<D>\d{2})_(?P<hhmm>\d{4})\.dat$"
)

def parse_hourly_filename(name: str) -> Optional[Tuple[str, str, str, str]]:
    m = HOURLY_RE.match(name)
    if not m:
        return None
    Y, M, D, hhmm = m.group("Y"), m.group("M"), m.group("D"), m.group("hhmm")
    day = f"{Y}-{M}-{D}"
    month = f"{Y}{M}"
    daily_name = f"{m.group('prefix')}{Y}_{M}_{D}_0000.dat"
    return day, month, daily_name, hhmm

def hour_sort_key(name: str) -> Tuple[int, int]:
    m = HOURLY_RE.match(name)
    if not m:
        return (9999, 9999)
    hhmm = int(m.group("hhmm"))
    return (hhmm // 100, hhmm % 100)

def rebuild_daily(sensor: str, day_str: str, groups: Dict[str, List[str]], raw_dir: str) -> int:
    month = day_str.replace("-", "")[:6]
    written = 0
    for daily_name, files in groups.items():
        files.sort(key=hour_sort_key)
        out_dir = os.path.join(LOCAL_BASE, sensor, month)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, daily_name)

        fd, tmp_path = tempfile.mkstemp(prefix=daily_name + ".", suffix=".part", dir=out_dir)
        os.close(fd)
        try:
            with open(tmp_path, "w", encoding="utf-8", newline="") as out_f:
                for i, fn in enumerate(files):
                    fp = os.path.join(raw_dir, fn)
                    with open(fp, "r", encoding="utf-8", errors="replace", newline="") as in_f:
                        for lineno, line in enumerate(in_f):
                            if i > 0 and lineno < TOA5_HEADER_LINES:
                                continue
                            out_f.write(line)
            os.replace(tmp_path, out_path)
            written += 1
            print(f"  Built: {out_path} ({len(files)} hourly files)")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    return written

def main():
    total_built = 0
    for sensor in SENSORS:
        raw_dir = os.path.join(LOCAL_BASE, RAW_SUBDIR, sensor)
        if not os.path.isdir(raw_dir):
            print(f"[{sensor}] No raw directory, skipping.")
            continue

        # Index existing daily files
        existing_daily = set()
        sensor_dir = os.path.join(LOCAL_BASE, sensor)
        for month_dir in os.listdir(sensor_dir):
            month_path = os.path.join(sensor_dir, month_dir)
            if not os.path.isdir(month_path):
                continue
            for fn in os.listdir(month_path):
                parsed = parse_hourly_filename(fn)
                if parsed:
                    existing_daily.add(parsed[2])  # daily_name

        # Group raw files by day and daily_name
        day_groups: Dict[str, Dict[str, List[str]]] = {}
        for fn in os.listdir(raw_dir):
            parsed = parse_hourly_filename(fn)
            if not parsed:
                continue
            day, _month, daily_name, _hhmm = parsed
            day_groups.setdefault(day, {}).setdefault(daily_name, []).append(fn)

        # Find days with at least one missing daily file
        missing_days = []
        for day, groups in sorted(day_groups.items()):
            if any(dn not in existing_daily for dn in groups):
                missing_days.append((day, groups))

        if not missing_days:
            print(f"[{sensor}] All daily files present, nothing to backfill.")
            continue

        print(f"\n[{sensor}] Backfilling {len(missing_days)} missing day(s):")
        built = 0
        for day, groups in missing_days:
            built += rebuild_daily(sensor, day, groups, raw_dir)
        total_built += built
        print(f"[{sensor}] Done — {built} daily file(s) written.")

    print(f"\nBackfill complete. Total files written: {total_built}")

if __name__ == "__main__":
    main()

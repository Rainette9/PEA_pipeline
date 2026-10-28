#!/usr/bin/env python3
"""
Hourly FTP delta downloader + optional hourly->daily merge (no database).

Remote root layout:
  /SFC
  /BOTTOM
  /LOWER
  /UPPER
  /MRR_zipped   (ignored)

Inside each sensor folder are hourly *.dat CSV-text files like:
  peasfc_fast_2026_02_22_0000.dat
  peasfc_fast_2026_02_22_0100.dat
  ...
  peasfc_fast_2026_02_22_2300.dat

What it does:
- Connects to FTP/FTPS (TLS optional) with user+password
- Scans ONLY SFC, BOTTOM, LOWER, UPPER
- Downloads new/changed/missing hourly .dat files (delta sync)
- Stores state in a local JSON manifest (no DB)
- If --merge is enabled (default), concatenates all available hourly files per day
  into a daily file stored in monthly folders under each sensor:
    <LOCAL_OUT>/<SENSOR>/<YYYYMM>/<daily_name>.dat
  Example:
    ./data/SFC/202602/peasfc_fast_2026_02_22_0000.dat

Resilience:
- If FTP is unreachable for some runs, next run catches up.
- If some hours arrive late, the lookback window ensures they’re rechecked and
  daily files are rebuilt to include them.

Schedule it hourly with cron/systemd/Task Scheduler.
"""

from __future__ import annotations

import os
import sys
import json
import time
import shutil
import logging
import argparse
import tempfile
import re
from datetime import datetime, timedelta, timezone
from ftplib import FTP, FTP_TLS, error_perm
from typing import Dict, Iterable, List, Optional, Tuple
from logging.handlers import RotatingFileHandler


# -------------------------
# Configuration (edit me)
# -------------------------
CONFIG = {
    "host": "185.96.7.126",
    "port": 21,
    "username": "snowflux",
    "password": "[TOPSECRET]",          # or leave None and set env FTP_PASSWORD
    "use_tls": False,                                  # True for explicit FTPS (FTP_TLS)
    "timeout": 60,
    "passive": True,
    "encoding": "utf-8",

    # Remote base: where the sensor folders live. If login lands at the root shown in your example,
    # set this to "" or "/" (both usually work).
    "remote_base": "/Science/snowflux",

    # Only these folders will be mirrored
    "sensors": ["SFC", "BOTTOM", "LOWER", "UPPER"],

    # Local output root
    "local_base": "/data/disk1/shared/PEA/data",

    # Raw hourly mirror (kept so daily merge can rebuild safely)
    "raw_subdir": "_raw",

    # JSON manifest/state file (tracks downloaded files and metadata)
    "state_file": "/data/disk1/shared/PEA/data/ftp_sync_state.json",

    # How far back (days) to rescan for late arriving files and to rebuild dailies
    "lookback_days": 3,

    # Cap downloads per run (safety)
    "max_downloads_per_run": 10000,

    # Sleep after a failed download to avoid hammering server
    "retry_sleep_sec": 1.0,

    # Merge daily files by default
    "merge_enabled": True,

    # If True: daily file is rebuilt every run for days in lookback window
    # (recommended; simplest & robust for late data)
    "rebuild_daily_each_run": True,
}

# -------------------------
# Logging
# -------------------------
# File handler with size limit (5 MB) and 3 backup files
file_handler = RotatingFileHandler(
    "/data/disk1/shared/PEA/data/datasync.log",
    maxBytes=5*1024*1024,  # 5 MB
    backupCount=3,         # keep 3 old log files
)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[file_handler],
)
log = logging.getLogger("ftp-delta")

# -------------------------
# Filename pattern helpers
# -------------------------
# Example: peasfc_fast_2026_02_22_2300.dat
HOURLY_RE = re.compile(
    r"^(?P<prefix>.+?)(?P<Y>\d{4})_(?P<M>\d{2})_(?P<D>\d{2})_(?P<hhmm>\d{4})\.dat$"
)

def parse_hourly_filename(name: str) -> Optional[Tuple[str, str, str, str]]:
    """
    Returns (day_yyyy_mm_dd, month_yyyymm, daily_name, hhmm) if matches hourly pattern else None.
    daily_name uses *_0000.dat for that date (per your example).
    """
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
    hh = hhmm // 100
    mm = hhmm % 100
    return (hh, mm)

# -------------------------
# State (JSON manifest)
# -------------------------
def load_state(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "last_sync_iso": None,
        # key: remote_path -> {"size": int|None, "modify": "YYYYMMDDHHMMSS"|None, "downloaded_at": iso, "local_path": str}
        "files": {},
    }

def save_state(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, path)

# -------------------------
# FTP utilities
# -------------------------
def ensure_local_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def safe_join_remote(*parts: str) -> str:
    joined = "/".join(p.strip("/").replace("//", "/") for p in parts if p not in (None, "", "/"))
    if not joined:
        return "/"
    return "/" + joined if not joined.startswith("/") else joined

def _safe_cwd(ftp, path: str) -> bool:
    try:
        ftp.cwd(path)
        return True
    except Exception:
        return False

def _listdir_names(ftp, path: str) -> List[str]:
    names: List[str] = []
    try:
        ftp.retrlines(f"NLST {path}", names.append)
    except Exception:
        try:
            lines: List[str] = []
            ftp.retrlines(f"LIST {path}", lines.append)
            for ln in lines:
                parts = ln.split(maxsplit=8)
                if len(parts) == 9:
                    names.append(parts[8])
        except Exception:
            pass
    return names

def connect():
    cls = FTP_TLS if CONFIG["use_tls"] else FTP
    ftp = cls()
    ftp.connect(CONFIG["host"], CONFIG["port"], timeout=CONFIG["timeout"])
    ftp.login(CONFIG["username"], get_password())

    # behavior niceties
    try:
        ftp.set_pasv(CONFIG.get("passive", True))
    except Exception:
        pass
    try:
        ftp.encoding = CONFIG.get("encoding", "utf-8")
    except Exception:
        pass
    if CONFIG["use_tls"]:
        ftp.prot_p()

    # Try to land in remote_base (robustly)
    remote_base = (CONFIG.get("remote_base") or "").strip()
    home = "/"
    try:
        home = ftp.pwd()
    except Exception:
        pass

    candidates: List[str] = []
    if remote_base:
        candidates.extend([
            remote_base,
            "/" + remote_base.lstrip("/"),
            (home.rstrip("/") + "/" + remote_base.lstrip("/")) if home else None,
        ])
    else:
        candidates.append(home)
        candidates.append("/")  # also try root

    seen = set()
    cand_list: List[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            cand_list.append(c)

    for cand in cand_list:
        if _safe_cwd(ftp, cand):
            return ftp

    try:
        current = ftp.pwd()
    except Exception:
        current = "(unknown)"
    root_listing = _listdir_names(ftp, ".")
    raise RuntimeError(
        "Could not change into any remote_base candidates.\n"
        f"  Provided remote_base: {remote_base!r}\n"
        f"  FTP home (pwd): {home!r}\n"
        f"  Tried candidates: {cand_list}\n"
        f"  Current dir after login: {current!r}\n"
        f"  Listing here shows: {root_listing[:20]} (first 20 entries)\n"
        "Hint: set CONFIG['remote_base'] to '' (login home), a relative name like 'data', "
        "or an absolute path like '/data'."
    )

def ftp_supports_mlsd(ftp: FTP) -> bool:
    # Try MLSD directly; many servers don't advertise it reliably via FEAT.
    try:
        list(ftp.mlsd("."))
        return True
    except Exception:
        return False

def list_dir_mlsd(ftp: FTP, path: str) -> List[Tuple[str, dict]]:
    ftp.cwd(path)
    out: List[Tuple[str, dict]] = []
    for name, facts in ftp.mlsd():
        out.append((name, facts))
    return out

def list_dir_list(ftp: FTP, path: str) -> List[Tuple[str, dict]]:
    ftp.cwd(path)
    lines: List[str] = []
    ftp.retrlines("LIST", lines.append)
    entries: List[Tuple[str, dict]] = []
    for line in lines:
        parts = line.split(maxsplit=8)
        if len(parts) < 9:
            continue
        kind = "dir" if parts[0].startswith("d") else "file"
        size = None
        try:
            size = int(parts[4])
        except Exception:
            pass
        name = parts[8]
        entries.append((name, {"type": kind, "size": size, "modify": None}))
    return entries

def ftp_mdtm(ftp: FTP, remote_path: str) -> Optional[str]:
    try:
        resp = ftp.sendcmd(f"MDTM {remote_path}")
        if resp.startswith("213 "):
            return resp.split()[1].strip()
    except Exception:
        return None
    return None

# -------------------------
# Download / delta logic
# -------------------------
def normalize_facts(name: str, facts: dict) -> dict:
    """
    Normalize to {type, size(int|None), modify(str|None)}
    facts from MLSD can include: type, size, modify (YYYYMMDDHHMMSS)
    """
    ftype = facts.get("type")
    if ftype in (None, "") and "perm" in facts:
        # no good info; ignore
        ftype = ""
    size = None
    if "size" in facts:
        try:
            size = int(facts["size"])
        except Exception:
            size = None
    modify = facts.get("modify")
    return {"type": ftype, "size": size, "modify": modify}

def should_download(remote_path: str, facts: dict, state: dict, local_path: str) -> bool:
    # Redownload if:
    # - never seen
    # - size differs (when available)
    # - modify differs (when available)
    # - local file missing
    old = state["files"].get(remote_path)
    if old is None:
        return True
    if not os.path.exists(local_path):
        return True
    size = facts.get("size")
    modify = facts.get("modify")
    if size is not None and old.get("size") is not None and old.get("size") != size:
        return True
    if modify and old.get("modify") and old.get("modify") != modify:
        return True
    return False

def atomic_download(ftp: FTP, remote_path: str, local_path: str) -> None:
    ensure_local_dir(os.path.dirname(local_path))
    tmp_dir = os.path.dirname(local_path) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=os.path.basename(local_path) + ".", suffix=".part", dir=tmp_dir)
    os.close(fd)
    try:
        with open(tmp_path, "wb") as f:
            ftp.retrbinary(f"RETR {remote_path}", f.write, blocksize=1024 * 256)
        os.replace(tmp_path, local_path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

def raw_local_path(sensor: str, filename: str) -> str:
    return os.path.join(CONFIG["local_base"], CONFIG["raw_subdir"], sensor, filename)

def scan_and_sync_sensor(ftp: FTP, sensor: str, state: dict, use_mlsd: bool, download_budget: int) -> int:
    """
    Returns number of downloads performed for this sensor.
    """
    remote_sensor = safe_join_remote(CONFIG["remote_base"], sensor)
    log.info("Scanning remote folder: %s", remote_sensor)

    try:
        entries = list_dir_mlsd(ftp, remote_sensor) if use_mlsd else list_dir_list(ftp, remote_sensor)
    except error_perm as e:
        log.warning("Cannot access %s: %s", remote_sensor, e)
        return 0

    downloads = 0
    for name, facts in entries:
        if downloads >= download_budget:
            break

        # Only files ending in .dat
        if name in (".", ".."):
            continue

        nfacts = normalize_facts(name, facts)
        ftype = nfacts.get("type", "")
        if ftype and ftype != "file":
            continue
        if not name.lower().endswith(".dat"):
            continue

        remote_path = safe_join_remote(remote_sensor, name)

        # Fill missing modify with MDTM if possible (especially on LIST fallback)
        if not nfacts.get("modify"):
            mdtm = ftp_mdtm(ftp, remote_path)
            if mdtm:
                nfacts["modify"] = mdtm

        local_path = raw_local_path(sensor, name)

        if should_download(remote_path, nfacts, state, local_path):
            log.info("Downloading: %s", remote_path)
            try:
                atomic_download(ftp, remote_path, local_path)
                state["files"][remote_path] = {
                    "size": nfacts.get("size"),
                    "modify": nfacts.get("modify"),
                    "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "local_path": os.path.abspath(local_path),
                }
                downloads += 1
            except Exception as e:
                log.warning("Download failed (%s): %s", remote_path, e)
                time.sleep(CONFIG["retry_sleep_sec"])

    return downloads

# -------------------------
# Daily merge
# -------------------------
def days_to_rebuild(now_utc: datetime) -> List[datetime]:
    start = (now_utc - timedelta(days=CONFIG["lookback_days"])).replace(hour=0, minute=0, second=0, microsecond=0)
    end = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    out = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur += timedelta(days=1)
    return out

def rebuild_daily_for_sensor(sensor: str, day_dt: datetime) -> int:
    """
    Rebuild daily files for the given sensor and UTC day.
    Returns number of daily files written (0/1 usually; can be >1 if multiple prefixes exist).
    """
    raw_dir = os.path.join(CONFIG["local_base"], CONFIG["raw_subdir"], sensor)
    if not os.path.isdir(raw_dir):
        return 0

    day_str = day_dt.strftime("%Y-%m-%d")
    month = day_dt.strftime("%Y%m")

    # Group hourly files by daily_name (handles multiple prefixes per day automatically)
    groups: Dict[str, List[str]] = {}
    for fn in os.listdir(raw_dir):
        parsed = parse_hourly_filename(fn)
        if not parsed:
            continue
        p_day, p_month, daily_name, _hhmm = parsed
        if p_day != day_str:
            continue
        groups.setdefault(daily_name, []).append(fn)

    written = 0
    for daily_name, files in groups.items():
        files.sort(key=hour_sort_key)
        out_dir = os.path.join(CONFIG["local_base"], sensor, month)
        ensure_local_dir(out_dir)
        out_path = os.path.join(out_dir, daily_name)

        # Atomic rebuild
        fd, tmp_path = tempfile.mkstemp(prefix=daily_name + ".", suffix=".part", dir=out_dir)
        os.close(fd)
        try:
            with open(tmp_path, "wb") as out_f:
                for fn in files:
                    fp = os.path.join(raw_dir, fn)
                    with open(fp, "rb") as in_f:
                        shutil.copyfileobj(in_f, out_f, length=1024 * 1024)
            os.replace(tmp_path, out_path)
            written += 1
            log.info("Built daily: %s (%d hourly files)", out_path, len(files))
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    return written

# -------------------------
# Password helper
# -------------------------
def get_password() -> str:
    pw = CONFIG.get("password")
    if pw:
        return pw
    env_pw = os.environ.get("FTP_PASSWORD")
    if env_pw:
        return env_pw
    raise RuntimeError("No FTP password: set CONFIG['password'] or environment variable FTP_PASSWORD")

# -------------------------
# Main
# -------------------------
def main():
    ap = argparse.ArgumentParser(description="Hourly FTP delta downloader + daily merge (no DB)")
    ap.add_argument("--dry-run", action="store_true", help="List actions, but do not download or write state")
    ap.add_argument("--no-merge", action="store_true", help="Disable hourly->daily merge")
    ap.add_argument("--lookback-days", type=int, default=None, help="Override lookback window (days)")
    ap.add_argument("-v", "--verbose", action="count", default=0, help="Increase logging verbosity (-v, -vv)")
    args = ap.parse_args()

    if args.verbose >= 2:
        log.setLevel(logging.DEBUG)
    elif args.verbose == 1:
        log.setLevel(logging.INFO)
    else:
        log.setLevel(logging.INFO)

    if args.lookback_days is not None:
        CONFIG["lookback_days"] = int(args.lookback_days)

    merge_enabled = CONFIG.get("merge_enabled", True) and (not args.no_merge)

    ensure_local_dir(CONFIG["local_base"])
    ensure_local_dir(os.path.join(CONFIG["local_base"], CONFIG["raw_subdir"]))

    state = load_state(CONFIG["state_file"])
    now = datetime.now(timezone.utc)

    log.info("Starting sync at %s (UTC)", now.isoformat())
    log.info("Sensors: %s", ", ".join(CONFIG["sensors"]))
    log.info("Remote base: %r", CONFIG.get("remote_base", ""))
    log.info("Local base: %s", os.path.abspath(CONFIG["local_base"]))
    log.info("State file: %s", os.path.abspath(CONFIG["state_file"]))
    log.info("Lookback days: %d", CONFIG["lookback_days"])
    log.info("Merge enabled: %s", merge_enabled)

    if args.dry_run:
        log.info("Dry-run mode enabled: no downloads, no state writes, no merges.")
        return

    ftp = None
    downloads_total = 0
    try:
        ftp = connect()
        use_mlsd = ftp_supports_mlsd(ftp)
        log.info("Using MLSD: %s", use_mlsd)

        budget = int(CONFIG["max_downloads_per_run"])
        for sensor in CONFIG["sensors"]:
            if budget <= 0:
                break
            d = scan_and_sync_sensor(ftp, sensor, state, use_mlsd, download_budget=budget)
            downloads_total += d
            budget -= d

        state["last_sync_iso"] = datetime.now(timezone.utc).isoformat()
        save_state(CONFIG["state_file"], state)
        log.info("Sync complete. Downloaded %d file(s).", downloads_total)

    except Exception as e:
        log.error("Run failed: %s", e)
        # Do not update last_sync_iso on failure; keep old state so it retries
        # (we still keep any successful file entries already written to state)
        with contextlib_suppress_exceptions():
            save_state(CONFIG["state_file"], state)
        raise
    finally:
        try:
            if ftp:
                ftp.quit()
        except Exception:
            pass

    # Merge (after successful download pass)
    if merge_enabled:
        built = 0
        for day_dt in days_to_rebuild(datetime.now(timezone.utc)):
            for sensor in CONFIG["sensors"]:
                built += rebuild_daily_for_sensor(sensor, day_dt)
        log.info("Merge complete. Wrote %d daily file(s).", built)

# Tiny helper to avoid importing contextlib just for suppress
class contextlib_suppress_exceptions:
    def __enter__(self):  # noqa
        return self
    def __exit__(self, exc_type, exc, tb):  # noqa
        return True

if __name__ == "__main__":
    main()

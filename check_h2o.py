#!/usr/bin/env python3
"""
Plausibility checks for the Peddy-processed H2O (LI-7500, mmol m-3).

For every hourly file ({S}_Fastdata_proc_YYYY-MM-DD_HHMM.dat) the hourly mean H2O
and sonic temperature Ts give an implied relative humidity:
    e  = H2O/1000 * 8.314 * (Ts + 273.15)          [Pa]
    es = 611.2 * exp(17.67 Ts / (Ts + 243.5))      [Pa]
    RH = 100 e / es
Expected medians ~30-60 % following the probe RH; no negative H2O, nothing > 400.

Usage:
  check_h2o.py summary DIR [DIR ...]            per-month summary (DIR = processed_HF/SENSOR or a month dir)
  check_h2o.py days DIR DATE [DATE ...]         per-hour table for given dates (YYYY-MM-DD)
  check_h2o.py compare DIR_A DIR_B              per-hour Pearson r and mean difference for files present in both
"""
import glob, math, os, sys
import numpy as np

def load(fname):
    with open(fname) as fh:
        hdr = fh.readline().strip().split(",")
    if "H2O" not in hdr:
        return None, None
    ih, it = hdr.index("H2O"), hdr.index("Ts")
    try:
        a = np.loadtxt(fname, delimiter=",", skiprows=1, usecols=(ih, it), ndmin=2)
    except Exception as e:
        print(f"  cannot read {fname}: {e}", file=sys.stderr)
        return None, None
    return a[:, 0], a[:, 1]

def implied_rh(h2o, ts):
    e = h2o / 1000.0 * 8.314 * (ts + 273.15)
    es = 611.2 * math.exp(17.67 * ts / (ts + 243.5))
    return 100.0 * e / es

def hour_stats(fname):
    h2o, ts = load(fname)
    if h2o is None:
        return None
    n = len(h2o)
    ok = ~np.isnan(h2o)
    nan_share = 1 - ok.sum() / max(n, 1)
    neg = int((h2o[ok] < 0).sum()); big = int((h2o[ok] > 400).sum())
    both = ok & ~np.isnan(ts)
    if both.sum() < 100:
        return dict(n=n, nan=nan_share, neg=neg, big=big, mean=np.nan, ts=np.nan, rh=np.nan,
                    vmin=np.nanmin(h2o) if ok.any() else np.nan, vmax=np.nanmax(h2o) if ok.any() else np.nan)
    m = float(h2o[both].mean()); t = float(ts[both].mean())
    return dict(n=n, nan=nan_share, neg=neg, big=big, mean=m, ts=t, rh=implied_rh(m, t),
                vmin=float(h2o[ok].min()), vmax=float(h2o[ok].max()))

def files_in(d):
    fs = sorted(glob.glob(os.path.join(d, "*_Fastdata_proc_*.dat")))
    if not fs:
        fs = sorted(glob.glob(os.path.join(d, "*", "*_Fastdata_proc_*.dat")))
    return fs

def month_of(f):
    return os.path.basename(f).split("_proc_")[1][:7]

def cmd_summary(dirs):
    print(f"{'month':8} {'files':>6} {'nanShare':>9} {'medRH%':>7} {'p10RH':>6} {'p90RH':>6} {'medH2O':>7} {'min':>7} {'max':>7} {'neg':>6} {'>400':>6}")
    for d in dirs:
        bym = {}
        for f in files_in(d):
            st = hour_stats(f)
            if st is None:
                continue
            bym.setdefault(month_of(f), []).append(st)
        for m in sorted(bym):
            L = bym[m]
            rh = np.array([s["rh"] for s in L if not np.isnan(s["rh"])])
            mean = np.array([s["mean"] for s in L if not np.isnan(s["mean"])])
            vmin = np.nanmin([s["vmin"] for s in L]) if L else np.nan
            vmax = np.nanmax([s["vmax"] for s in L]) if L else np.nan
            nan = np.mean([s["nan"] for s in L])
            neg = sum(s["neg"] for s in L); big = sum(s["big"] for s in L)
            f = lambda x, p: f"{x:{p}}" if x == x else "   -"
            print(f"{m:8} {len(L):6d} {nan:9.1%} {f(np.median(rh) if rh.size else np.nan, '7.1f')} "
                  f"{f(np.percentile(rh,10) if rh.size else np.nan,'6.1f')} {f(np.percentile(rh,90) if rh.size else np.nan,'6.1f')} "
                  f"{f(np.median(mean) if mean.size else np.nan,'7.1f')} {f(vmin,'7.1f')} {f(vmax,'7.1f')} {neg:6d} {big:6d}")

def cmd_days(d, dates):
    print(f"{'hour':22} {'meanH2O':>8} {'Ts':>7} {'RH%':>6} {'nan':>6} {'min':>8} {'max':>10}")
    for f in files_in(d):
        base = os.path.basename(f)
        if not any(dt in base for dt in dates):
            continue
        st = hour_stats(f)
        if st is None:
            continue
        g = lambda x, p: f"{x:{p}}" if x == x else "-"
        print(f"{base.split('_proc_')[1][:15]:22} {g(st['mean'],'8.1f')} {g(st['ts'],'7.1f')} {g(st['rh'],'6.1f')} {st['nan']:6.0%} {g(st['vmin'],'8.1f')} {g(st['vmax'],'10.1f')}")

def cmd_compare(da, db):
    fa = {os.path.basename(f): f for f in files_in(da)}
    fb = {os.path.basename(f): f for f in files_in(db)}
    common = sorted(set(fa) & set(fb))
    print(f"{len(common)} common files")
    rs, dm = [], []
    print(f"{'hour':22} {'r':>6} {'meanA':>8} {'meanB':>8} {'diff':>7} {'nanA':>5} {'nanB':>5}")
    for k in common:
        a, _ = load(fa[k]); b, _ = load(fb[k])
        if a is None or b is None or len(a) != len(b):
            continue
        ok = ~np.isnan(a) & ~np.isnan(b)
        r = float(np.corrcoef(a[ok], b[ok])[0, 1]) if ok.sum() > 100 and a[ok].std() > 0 and b[ok].std() > 0 else np.nan
        ma = float(np.nanmean(a)) if (~np.isnan(a)).any() else np.nan
        mb = float(np.nanmean(b)) if (~np.isnan(b)).any() else np.nan
        if r == r: rs.append(r)
        if ma == ma and mb == mb: dm.append(mb - ma)
        print(f"{k.split('_proc_')[1][:15]:22} {r:6.3f} {ma:8.1f} {mb:8.1f} {mb-ma:7.2f} {np.isnan(a).mean():5.0%} {np.isnan(b).mean():5.0%}")
    if rs:
        print(f"median r = {np.median(rs):.3f}, min r = {min(rs):.3f}; median |diff| = {np.median(np.abs(dm)):.2f}, max |diff| = {max(np.abs(dm)):.2f} mmol/m3")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "summary": cmd_summary(sys.argv[2:])
    elif cmd == "days": cmd_days(sys.argv[2], sys.argv[3:])
    elif cmd == "compare": cmd_compare(sys.argv[2], sys.argv[3])
    else: print(__doc__); sys.exit(1)

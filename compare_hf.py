#!/usr/bin/env python3
"""
Compare two sets of processed hourly HF files (ICSV, 1 header row) hour by hour.

    python3 compare_hf.py DIR_A DIR_B [--date YYYY-MM-DD] [--sensor S]

For every file name present in both directories (optionally only one date) it reports per
variable: rows, NaN count in A and B, number of samples NaN in exactly one of them, and the
maximum absolute difference where both are finite. Used for the v3 equivalence check
(workstation merged code vs the PC's v3 output).
"""
import argparse
import math
import os
import sys


def read_icsv(path):
    with open(path) as f:
        header = f.readline().rstrip("\n").split(",")
        rows = [line.rstrip("\n").split(",") for line in f]
    cols = {h: [] for h in header}
    for r in rows:
        for h, v in zip(header, r):
            cols[h].append(v)
    return header, cols


def to_f(v):
    try:
        x = float(v)
    except ValueError:
        return math.nan
    return x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir_a")
    ap.add_argument("dir_b")
    ap.add_argument("--date")
    ap.add_argument("--sensor")
    a = ap.parse_args()
    fa = sorted(f for f in os.listdir(a.dir_a) if "Fastdata_proc" in f and (not a.date or a.date in f))
    fb = set(f for f in os.listdir(a.dir_b) if "Fastdata_proc" in f)
    common = [f for f in fa if f in fb]
    print(f"files: A={len(fa)} common={len(common)} (A only: {len(fa)-len(common)})")
    tot = {}
    for f in common:
        ha, ca = read_icsv(os.path.join(a.dir_a, f))
        hb, cb = read_icsv(os.path.join(a.dir_b, f))
        if ha != hb:
            print(f"{f}: header differs: {ha} vs {hb}")
            continue
        if ca["timestamp"] != cb["timestamp"]:
            print(f"{f}: timestamps differ ({len(ca['timestamp'])} vs {len(cb['timestamp'])} rows)")
            continue
        for h in ha[1:]:
            xa = [to_f(v) for v in ca[h]]
            xb = [to_f(v) for v in cb[h]]
            t = tot.setdefault(h, {"n": 0, "nan_a": 0, "nan_b": 0, "nan_xor": 0, "maxdiff": 0.0, "ndiff": 0})
            for p, q in zip(xa, xb):
                t["n"] += 1
                na, nb = math.isnan(p), math.isnan(q)
                t["nan_a"] += na
                t["nan_b"] += nb
                if na != nb:
                    t["nan_xor"] += 1
                elif not na:
                    d = abs(p - q)
                    if d > 0:
                        t["ndiff"] += 1
                    if d > t["maxdiff"]:
                        t["maxdiff"] = d
    print(f"{'var':10s} {'rows':>9s} {'NaN A':>8s} {'NaN B':>8s} {'NaN xor':>8s} {'values!=':>9s} {'max|diff|':>12s}")
    for h, t in tot.items():
        print(f"{h:10s} {t['n']:9d} {t['nan_a']:8d} {t['nan_b']:8d} {t['nan_xor']:8d} {t['ndiff']:9d} {t['maxdiff']:12.4g}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

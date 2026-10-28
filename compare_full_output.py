#!/usr/bin/env python3
"""
Compare two EddyPro full_output files row by row (key = date + time).

    python3 compare_full_output.py FILE_A FILE_B [--top N]

Prints the rows present in only one file, then per numeric column the number of rows where
both are valid (not -9999), the number of -9999 mismatches, the max absolute difference and the
max relative difference, sorted by relative difference. Used for the v3 EddyPro equivalence
check (workstation engine vs the PC's run on identical HF input).
"""
import argparse
import csv
import math
import sys

NODATA = -9999.0


def read(path):
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    names = rows[1]
    data = {}
    for r in rows[3:]:
        if len(r) < 3:
            continue
        data[(r[1], r[2])] = r
    return names, data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()
    na, da = read(args.a)
    nb, db = read(args.b)
    if na != nb:
        only_a = [c for c in na if c not in nb]
        only_b = [c for c in nb if c not in na]
        print(f"column sets differ: only in A {only_a[:10]}, only in B {only_b[:10]}")
    common_cols = [c for c in na if c in nb]
    ka, kb = set(da), set(db)
    print(f"rows: A={len(da)} B={len(db)} common={len(ka & kb)} A-only={len(ka - kb)} B-only={len(kb - ka)}")
    if ka - kb:
        print("  A-only (first 5):", sorted(ka - kb)[:5])
    if kb - ka:
        print("  B-only (first 5):", sorted(kb - ka)[:5])
    keys = sorted(ka & kb)
    ia = {c: na.index(c) for c in common_cols}
    ib = {c: nb.index(c) for c in common_cols}
    stats = []
    for c in common_cols:
        if c in ("filename", "date", "time"):
            continue
        n_both = n_mis = n_diff = 0
        maxabs = maxrel = 0.0
        for k in keys:
            try:
                x = float(da[k][ia[c]])
                y = float(db[k][ib[c]])
            except (ValueError, IndexError):
                continue
            xa, yb = x == NODATA or math.isnan(x), y == NODATA or math.isnan(y)
            if xa != yb:
                n_mis += 1
            elif not xa:
                n_both += 1
                d = abs(x - y)
                if d > 0:
                    n_diff += 1
                    maxabs = max(maxabs, d)
                    maxrel = max(maxrel, d / max(abs(x), abs(y), 1e-12))
        stats.append((maxrel, c, n_both, n_mis, n_diff, maxabs))
    stats.sort(reverse=True)
    print(f"{'column':28s} {'both':>6s} {'nodata!=':>9s} {'diff':>6s} {'max|d|':>12s} {'maxrel':>9s}")
    for maxrel, c, n_both, n_mis, n_diff, maxabs in stats[: args.top]:
        print(f"{c:28s} {n_both:6d} {n_mis:9d} {n_diff:6d} {maxabs:12.4g} {maxrel:9.2e}")
    identical = sum(1 for s in stats if s[4] == 0 and s[3] == 0)
    print(f"columns identical: {identical} / {len(stats)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Distribution of View B surface elongation across a whole run.

Three hand-picked dates is a cherry-pick, not a measurement. This walks
every Nth exported surface for a ticker and reports the spread, so the
claim about what shape these things are is about the run rather than
about whichever date happened to be typed first.
"""
import glob
import os
import sys
import struct
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mesh_shape import read_gmmesh, principal_extents  # noqa: E402


def summarize(paths):
    ratios = []
    for p in paths:
        try:
            _, verts, _ = read_gmmesh(p)
        except Exception:
            continue
        e = principal_extents(verts)
        if e[1] > 0:
            ratios.append((e[0] / e[1], os.path.basename(p)))
    return sorted(ratios)


if __name__ == '__main__':
    surfaces = sys.argv[1]
    every = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    for ticker in ('AAPL', 'NVDA', 'XOM'):
        files = sorted(glob.glob(os.path.join(surfaces, '*_B_%s.gmmesh' % ticker)))[::every]
        if not files:
            continue
        r = summarize(files)
        if not r:
            continue
        vals = [x[0] for x in r]
        n = len(vals)
        print('%-5s n=%-4d  long:mid  min %.2f  p25 %.2f  median %.2f  p75 %.2f  max %.2f'
              % (ticker, n, vals[0], vals[n // 4], vals[n // 2], vals[3 * n // 4], vals[-1]))
        print('        most elongated: %s (%.2f)' % (r[-1][1], r[-1][0]))
        print('        fraction above 2.0 (visibly a tube): %.0f%%'
              % (100.0 * sum(1 for v in vals if v >= 2.0) / n))

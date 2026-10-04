#!/usr/bin/env python3
"""Compare a benchmark run against the committed baseline. ADR-020 layer 4.

    tools/check_benchmarks.py bench.json tests/benchmarks/baseline.json

WHY THIS COMPARES SHAPES, NOT NANOSECONDS
-----------------------------------------
The committed baseline was recorded on one machine. CI runs on a shared
runner several times slower, and a laptop on battery is slower again. An
absolute-time gate would therefore fail on every machine except the one
that produced the baseline, and a gate that always fails gets switched
off - which is worse than having none.

So the gate compares each benchmark against the run's own geometric mean.
That is the SHAPE of the run: how much of the frame loop each piece
accounts for, relative to the rest. Machine speed divides out of it
entirely, and what survives is exactly what a code regression looks like -
one component growing relative to its neighbours.

WHAT THIS DELIBERATELY CANNOT SEE, stated plainly: a change that slows
EVERYTHING by the same factor - a compiler flag, a switch to a debug
allocator, an Eigen version that is uniformly worse - leaves the shape
unchanged and passes. That is the price of machine-independence. The
absolute times are printed alongside every ratio for exactly that reason:
the gate does not enforce them, and a human reading the log can still see
that the whole run went from 400us to 900us.

A benchmark present in the baseline but missing from the run is an ERROR,
not a pass. Deleting a benchmark is the easiest way to make a regression
disappear, and it should never be the quiet option.
"""
import argparse
import json
import math
import sys


def load(path):
    with open(path) as f:
        doc = json.load(f)
    out = {}
    for entry in doc.get('benchmarks', []):
        # Skip google-benchmark's aggregate rows (mean/median/stddev):
        # comparing an aggregate against a raw run compares two different
        # quantities.
        if entry.get('run_type') == 'aggregate':
            continue
        out[entry['name']] = float(entry['real_time'])
    return out


def geometric_mean(values):
    """Geometric, not arithmetic: these times span three orders of
    magnitude (Procrustes ~0.8us, MDS ~300us), and an arithmetic mean over
    that is just the largest one, which would make the normalisation
    meaningless for everything else."""
    logs = [math.log(v) for v in values if v > 0]
    if not logs:
        return 0.0
    return math.exp(sum(logs) / len(logs))


def normalised(times):
    scale = geometric_mean(list(times.values()))
    if scale <= 0:
        return {}
    return {name: t / scale for name, t in times.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('current')
    ap.add_argument('baseline')
    ap.add_argument('--threshold', type=float, default=0.20,
                    help='fractional growth in a benchmark\'s share of the run that fails '
                         'the gate (default 0.20)')
    args = ap.parse_args()

    current = load(args.current)
    baseline = load(args.baseline)
    if not baseline:
        sys.exit('baseline %s has no benchmarks in it' % args.baseline)

    missing = sorted(set(baseline) - set(current))
    shared = sorted(set(baseline) & set(current))
    if not shared:
        sys.exit('no benchmark names in common between the two runs')

    # Normalise over the SHARED set only, so a benchmark added or removed
    # cannot move the scale and make every other row look like it changed.
    cur_norm = normalised({k: current[k] for k in shared})
    base_norm = normalised({k: baseline[k] for k in shared})

    cur_total = sum(current[k] for k in shared)
    base_total = sum(baseline[k] for k in shared)

    print('%-28s %11s %11s %9s %9s %8s'
          % ('benchmark', 'base ns', 'now ns', 'base share', 'now share', 'ratio'))
    print('-' * 82)
    regressions = []
    for name in shared:
        ratio = cur_norm[name] / base_norm[name] if base_norm[name] > 0 else float('inf')
        flag = ''
        if ratio > 1.0 + args.threshold:
            regressions.append((name, ratio))
            flag = '  <-- REGRESSION'
        print('%-28s %11.0f %11.0f %9.3f %9.3f %7.2fx%s'
              % (name, baseline[name], current[name], base_norm[name], cur_norm[name],
                 ratio, flag))

    # Absolute wall time, reported and NOT gated - see the module docstring.
    if base_total > 0:
        print('\nTotal across shared benchmarks: %.0f ns baseline -> %.0f ns now (%.2fx). '
              'Not gated: machine speed.' % (base_total, cur_total, cur_total / base_total))

    new = sorted(set(current) - set(baseline))
    if new:
        print('\nNot in the baseline (regenerate it to include them):')
        for name in new:
            print('    %s' % name)

    if missing:
        print('\nERROR: in the baseline but absent from this run:')
        for name in missing:
            print('    %s' % name)
        print('Deleting a benchmark is the easiest way to make a regression '
              'disappear; that is why this is an error.')
        return 1

    if regressions:
        print('\nFAILED: %d benchmark(s) grew more than %.0f%% as a share of the run.'
              % (len(regressions), 100 * args.threshold))
        return 1

    print('\nOK: no benchmark grew more than %.0f%% as a share of the run.'
          % (100 * args.threshold))
    return 0


if __name__ == '__main__':
    sys.exit(main())

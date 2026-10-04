#!/usr/bin/env python3
"""Is the View B surface actually a tube?

'It wrote files and the counters went up' proves the plumbing, not the
shape. A View B surface fitted to a path through space should be
elongated - one principal axis much longer than the others - while a
View A surface fitted to a cross-sectional cloud should be comparatively
round. If both came out round, something is fitting the wrong training
set and the pictures would look plausible and be wrong.
"""
import struct
import sys
import math


def read_gmmesh(path):
    with open(path, 'rb') as f:
        blob = f.read()
    assert blob[:6] == b'GMMESH', 'bad magic in ' + path
    version, = struct.unpack_from('<H', blob, 6)
    nv, nt = struct.unpack_from('<QQ', blob, 8)
    off = 24
    verts = struct.unpack_from('<%dd' % (nv * 3), blob, off)
    off += nv * 3 * 8
    tris = struct.unpack_from('<%dI' % (nt * 3), blob, off)
    return version, [verts[i:i + 3] for i in range(0, len(verts), 3)], nt


def principal_extents(points):
    """Std deviation along each principal axis, largest first."""
    n = len(points)
    mean = [sum(p[k] for p in points) / n for k in range(3)]
    cov = [[0.0] * 3 for _ in range(3)]
    for p in points:
        d = [p[k] - mean[k] for k in range(3)]
        for i in range(3):
            for j in range(3):
                cov[i][j] += d[i] * d[j]
    for i in range(3):
        for j in range(3):
            cov[i][j] /= n

    # Jacobi eigenvalues for a 3x3 symmetric matrix - small enough to do
    # by hand rather than pull in numpy, which is not installed here.
    a = [row[:] for row in cov]
    for _ in range(60):
        # largest off-diagonal
        p, q, best = 0, 1, 0.0
        for i in range(3):
            for j in range(i + 1, 3):
                if abs(a[i][j]) > best:
                    best, p, q = abs(a[i][j]), i, j
        if best < 1e-18:
            break
        theta = 0.5 * math.atan2(2 * a[p][q], a[q][q] - a[p][p])
        c, s = math.cos(theta), math.sin(theta)
        for k in range(3):
            akp = c * a[k][p] - s * a[k][q]
            akq = s * a[k][p] + c * a[k][q]
            a[k][p], a[k][q] = akp, akq
        for k in range(3):
            apk = c * a[p][k] - s * a[q][k]
            aqk = s * a[p][k] + c * a[q][k]
            a[p][k], a[q][k] = apk, aqk
    eig = sorted((a[i][i] for i in range(3)), reverse=True)
    return [math.sqrt(max(e, 0.0)) for e in eig]


def report(label, path):
    version, verts, nt = read_gmmesh(path)
    ext = principal_extents(verts)
    # long:short alone does NOT distinguish a tube from a flattened disc -
    # a pancake scores just as high on it. A cigar is long relative to its
    # SECOND axis; a pancake is not. Both numbers, or the conclusion is a
    # guess dressed as a measurement.
    cigar = ext[0] / ext[1] if ext[1] > 0 else float('inf')
    flat = ext[1] / ext[2] if ext[2] > 0 else float('inf')
    shape = 'cigar' if cigar >= 2.0 else ('pancake' if flat >= 2.0 else 'round')
    print('%-8s %6d verts %6d tris  extents %.4f/%.4f/%.4f  long:mid=%.2f  mid:short=%.2f  -> %s'
          % (label, len(verts), nt, ext[0], ext[1], ext[2], cigar, flat, shape))
    return cigar, flat


if __name__ == '__main__':
    a_cigar, a_flat = report('View A', sys.argv[1])
    b_cigar, b_flat = report('View B', sys.argv[2])
    print()
    print('View B is %.2fx more cigar-shaped than View A (long:mid ratio)'
          % (b_cigar / a_cigar))

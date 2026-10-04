"""Correlation-tree research adaptation of Lattice's distance graph.

Edges minimize sqrt(2*(1-rho)), preserving the sign of correlation. The
covariance adaptation uses products of edge correlations along tree paths.
It is not Lattice's RIE estimator, LoGo, a causal graph, or an alpha forecast.
"""
from __future__ import annotations
import numpy as np


def _matrix(values):
    data = np.asarray(values, dtype=float)
    if (data.ndim != 2 or not len(data) or data.shape[0] != data.shape[1]
            or not np.isfinite(data).all() or not np.allclose(data, data.T, atol=1e-10)):
        raise ValueError('finite symmetric nonempty square matrix required')
    return data


def mst_neighbors(correlation):
    corr = _matrix(correlation)
    if not np.allclose(np.diag(corr), 1.) or np.abs(corr).max() > 1. + 1e-10:
        raise ValueError('correlation diagonal/bounds invalid')
    size = len(corr)
    parent = list(range(size))
    neighbors = [[] for _ in range(size)]

    def root(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    # Kruskal; monotonic correlation distance permits sorting by -rho.
    edges = sorted((-float(corr[i, j]), i, j)
                   for i in range(size) for j in range(i + 1, size))
    accepted = 0
    for _, left, right in edges:
        a, b = root(left), root(right)
        if a == b:
            continue
        parent[a] = b
        neighbors[left].append(right)
        neighbors[right].append(left)
        accepted += 1
        if accepted == size - 1:
            break
    return [sorted(nodes) for nodes in neighbors]


def tree_covariance(covariance):
    cov = _matrix(covariance)
    variances = np.diag(cov)
    if (variances <= 0).any():
        raise ValueError('positive variances required')
    scales = np.sqrt(variances)
    corr = cov / np.outer(scales, scales)
    neighbors = mst_neighbors(corr)
    result = np.eye(len(cov))
    for origin in range(len(cov)):
        pending = [(origin, -1, 1.)]
        while pending:
            node, previous, product = pending.pop()
            result[origin, node] = product
            for other in neighbors[node]:
                if other != previous:
                    edge = np.clip(corr[node, other], -1. + 1e-8, 1. - 1e-8)
                    pending.append((other, node, product * edge))
    return result * np.outer(scales, scales)

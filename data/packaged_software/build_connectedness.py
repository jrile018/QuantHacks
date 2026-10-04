"""Connectedness metrics for the 168-company universe (checklist section 14).

Builds five independent edge layers, then measures how connected each company is and how
connected the network is as a whole. The layers measure different things and are kept
separate as well as combined, because a company can be central in news coverage and
peripheral in disclosure, and averaging that away hides the distinction.

Layers
  news_comention   two companies named in the same news article. Each article contributes
                   weight 1/(k-1) to each of its pairs, so a two-company article counts for
                   much more than a market roundup. Articles naming more than
                   MAX_TICKERS_PER_ARTICLE companies are dropped entirely as roundups.
  tenk_mention     one company names another in its 10-K. Directed; symmetrized for the
                   undirected metrics. Only matches that included the legal suffix are used,
                   because the bare-name form matched ordinary phrases
                   ("Quantum Computing Inc." reduced to "Quantum Computing").
  return_corr      Pearson correlation of daily returns over the window. Correlation
                   networks are dense by construction, so the threshold is swept and the
                   density at each level is reported rather than one arbitrary cut.
  shared_auditor   both audited by the same firm. A weak tie, included because auditor
                   changes and restatements cluster by firm.
  shared_agency    both hold federal awards from the same awarding agency.

Metrics per company: degree, strength (weighted degree), eigenvector centrality, PageRank,
local clustering, k-core, betweenness (Brandes), and ICM influence.

ICM influence is an Independent Cascade simulation: the company is activated, each active
node gets one chance to activate each neighbour with probability proportional to the edge
weight, and the reported figure is the mean number of companies reached. It answers "if
something happens here, how far could it plausibly travel", which plain degree does not.

Network level: density, components, largest component, mean degree and clustering, and
degree assortativity.

Writes
  output/connectedness_edges.csv       one row per (layer, company pair, weight)
  output/connectedness_by_company.csv  one row per company per layer, plus a composite
  output/connectedness_network.csv     one row per layer: network-level summary

Caveat on interpretation: these are descriptive structure measures. A related study in
another lane of this project (peer reversion from a return-correlation distance matrix)
failed to show value at any horizon, so centrality here should not be read as a trading
signal without its own test.
"""

from __future__ import annotations

import csv
import random
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
EXTRACTS = HERE / "extracts"
MAX_TICKERS_PER_ARTICLE = 10
CORR_THRESHOLDS = (0.3, 0.5, 0.7)
CORR_EDGE_THRESHOLD = 0.5
MIN_OVERLAP_DAYS = 250
ICM_TRIALS = 200
ICM_SCALE = 0.3          # caps per-edge activation probability
RANDOM_SEED = 17


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- layers

def layer_news(universe: set[str]) -> dict[tuple[str, str], float]:
    edges: dict[tuple[str, str], float] = defaultdict(float)
    seen_articles: set[str] = set()
    for r in read(EXTRACTS / "company_news" / "news_articles.csv"):
        article = r.get("article_id", "")
        if article in seen_articles:
            continue
        seen_articles.add(article)
        tickers = sorted({t for t in (r.get("associated_tickers", "") or "").split(";") if t in universe})
        if len(tickers) < 2 or len(tickers) > MAX_TICKERS_PER_ARTICLE:
            continue
        weight = 1.0 / (len(tickers) - 1)
        for i, a in enumerate(tickers):
            for b in tickers[i + 1:]:
                edges[(a, b)] += weight
    return dict(edges)


def layer_tenk(universe: set[str]) -> dict[tuple[str, str], float]:
    edges: dict[tuple[str, str], float] = defaultdict(float)
    for r in read(OUT / "tenk_mention_network.csv"):
        if r.get("match_form") != "with_suffix":
            continue
        a, b = r["filer_ticker"], r["mentioned_ticker"]
        if a in universe and b in universe and a != b:
            edges[tuple(sorted((a, b)))] += float(r.get("mentions_with_legal_suffix") or 1)
    return dict(edges)


def layer_common_ownership(universe: set[str]) -> dict[tuple[str, str], float]:
    """13F common-ownership edges: mean cosine similarity of manager holdings across quarters,
    with passive managers removed upstream (build_common_ownership.py)."""
    edges = {}
    for r in read(OUT / "common_ownership_edges.csv"):
        a, b = r["company_a"], r["company_b"]
        if a in universe and b in universe and a != b:
            edges[tuple(sorted((a, b)))] = float(r["mean_cosine"])
    return edges


def return_correlations(universe: set[str]) -> tuple[list[str], np.ndarray]:
    """Correlation matrix of daily returns for companies with enough overlapping history."""
    closes: dict[str, dict[str, float]] = defaultdict(dict)
    for r in read(EXTRACTS / "prices" / "daily_bars.csv"):
        if r["ticker"] in universe and r["close"]:
            closes[r["ticker"]][r["date"]] = float(r["close"])
    dates = sorted({d for series in closes.values() for d in series})
    index = {d: i for i, d in enumerate(dates)}
    tickers = sorted(t for t, s in closes.items() if len(s) >= MIN_OVERLAP_DAYS)
    matrix = np.full((len(tickers), len(dates)), np.nan)
    for i, t in enumerate(tickers):
        for d, px in closes[t].items():
            matrix[i, index[d]] = px
    returns = np.diff(np.log(matrix), axis=1)
    # Pairwise correlation on overlapping non-missing days only
    n = len(tickers)
    corr = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            both = ~np.isnan(returns[i]) & ~np.isnan(returns[j])
            if both.sum() >= MIN_OVERLAP_DAYS:
                a, b = returns[i][both], returns[j][both]
                if a.std() > 0 and b.std() > 0:
                    corr[i, j] = corr[j, i] = float(np.corrcoef(a, b)[0, 1])
    return tickers, corr


def layer_corr(tickers: list[str], corr: np.ndarray, threshold: float) -> dict[tuple[str, str], float]:
    edges = {}
    for i in range(len(tickers)):
        for j in range(i + 1, len(tickers)):
            c = corr[i, j]
            if not np.isnan(c) and c >= threshold:
                edges[tuple(sorted((tickers[i], tickers[j])))] = float(c)
    return edges


def layer_shared_attribute(rows: list[dict], key_field: str, ticker_field: str,
                           universe: set[str], split: str | None = None) -> dict[tuple[str, str], float]:
    """Edges between companies sharing an attribute value (auditor, awarding agency)."""
    groups: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        ticker = r.get(ticker_field, "")
        value = (r.get(key_field) or "").strip()
        if not ticker or ticker not in universe or not value:
            continue
        for v in (value.split(split) if split else [value]):
            v = v.strip()
            if v:
                groups[v].add(ticker)
    edges: dict[tuple[str, str], float] = defaultdict(float)
    for members in groups.values():
        # A value shared by nearly everyone carries no information
        if len(members) < 2 or len(members) > len(universe) // 3:
            continue
        ordered = sorted(members)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                edges[(a, b)] += 1.0 / (len(ordered) - 1)
    return dict(edges)


# ---------------------------------------------------------------- graph metrics

def adjacency(nodes: list[str], edges: dict[tuple[str, str], float]) -> np.ndarray:
    idx = {t: i for i, t in enumerate(nodes)}
    A = np.zeros((len(nodes), len(nodes)))
    for (a, b), w in edges.items():
        if a in idx and b in idx:
            A[idx[a], idx[b]] = A[idx[b], idx[a]] = w
    return A


def eigenvector_centrality(A: np.ndarray, iterations: int = 200) -> np.ndarray:
    n = A.shape[0]
    if n == 0 or A.sum() == 0:
        return np.zeros(n)
    v = np.ones(n) / n
    for _ in range(iterations):
        nv = A @ v
        norm = np.linalg.norm(nv)
        if norm == 0:
            return np.zeros(n)
        nv /= norm
        if np.allclose(nv, v, atol=1e-10):
            break
        v = nv
    return np.abs(v)


def pagerank(A: np.ndarray, damping: float = 0.85, iterations: int = 200) -> np.ndarray:
    n = A.shape[0]
    if n == 0:
        return np.zeros(0)
    out = A.sum(axis=1)
    M = np.divide(A, out[:, None], out=np.zeros_like(A), where=out[:, None] > 0)
    r = np.ones(n) / n
    for _ in range(iterations):
        nr = (1 - damping) / n + damping * (M.T @ r)
        # dangling nodes spread their mass evenly
        nr += damping * r[out == 0].sum() / n
        nr /= nr.sum()
        if np.allclose(nr, r, atol=1e-12):
            break
        r = nr
    return r


def local_clustering(A: np.ndarray) -> np.ndarray:
    B = (A > 0).astype(float)
    np.fill_diagonal(B, 0)
    deg = B.sum(axis=1)
    triangles = np.diag(B @ B @ B) / 2
    possible = deg * (deg - 1) / 2
    return np.divide(triangles, possible, out=np.zeros_like(triangles), where=possible > 0)


def k_core(A: np.ndarray) -> np.ndarray:
    B = (A > 0).astype(bool).copy()
    np.fill_diagonal(B, False)
    n = B.shape[0]
    core = np.zeros(n, dtype=int)
    alive = np.ones(n, dtype=bool)
    k = 0
    while alive.any():
        while True:
            deg = (B[np.ix_(alive, alive)]).sum(axis=1)
            low = deg <= k
            if not low.any():
                break
            idx = np.where(alive)[0][low]
            core[idx] = k
            alive[idx] = False
            if not alive.any():
                break
        k += 1
    return core


def betweenness(A: np.ndarray) -> np.ndarray:
    """Brandes betweenness on the unweighted graph. 168 nodes, so the exact form is fine."""
    n = A.shape[0]
    neighbours = [np.where(A[i] > 0)[0] for i in range(n)]
    bc = np.zeros(n)
    for s in range(n):
        stack, pred, sigma, dist = [], [[] for _ in range(n)], np.zeros(n), np.full(n, -1)
        sigma[s], dist[s] = 1, 0
        queue = [s]
        while queue:
            v = queue.pop(0)
            stack.append(v)
            for w in neighbours[v]:
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        delta = np.zeros(n)
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                bc[w] += delta[w]
    if n > 2:
        bc /= ((n - 1) * (n - 2))
    return bc


def icm_influence(A: np.ndarray, trials: int = ICM_TRIALS, scale: float = ICM_SCALE,
                  uniform: bool = True) -> np.ndarray:
    """Mean companies reached by an Independent Cascade seeded at each company.

    With uniform=True every edge transmits with the same probability, so the result reflects
    topology alone and is comparable across layers. Scaling probability by weight/max made
    the layers incomparable: news weights are long-tailed, so dividing by the maximum pushed
    almost every edge to near zero (mean reach 1.10), while the correlation layer's weights
    cluster near its maximum and spread to 22 companies. Same topology, different units.

    The figure includes the seed, so the minimum is 1.
    """
    n = A.shape[0]
    if n == 0:
        return np.zeros(0)
    if uniform:
        P = (A > 0).astype(float) * scale
    else:
        top = A.max() if A.max() > 0 else 1.0
        P = (A / top) * scale
    rng = random.Random(RANDOM_SEED)
    neighbours = [np.where(A[i] > 0)[0] for i in range(n)]
    reached = np.zeros(n)
    for seed in range(n):
        total = 0
        for _ in range(trials):
            active = {seed}
            frontier = [seed]
            while frontier:
                nxt = []
                for v in frontier:
                    for w in neighbours[v]:
                        if w not in active and rng.random() < P[v, w]:
                            active.add(int(w))
                            nxt.append(int(w))
                frontier = nxt
            total += len(active)
        reached[seed] = total / trials
    return reached


def components(A: np.ndarray) -> list[list[int]]:
    n = A.shape[0]
    seen, out = set(), []
    for start in range(n):
        if start in seen:
            continue
        stack, comp = [start], []
        seen.add(start)
        while stack:
            v = stack.pop()
            comp.append(v)
            for w in np.where(A[v] > 0)[0]:
                if w not in seen:
                    seen.add(int(w))
                    stack.append(int(w))
        out.append(sorted(comp))
    return sorted(out, key=len, reverse=True)


def assortativity(A: np.ndarray) -> float:
    B = (A > 0).astype(float)
    np.fill_diagonal(B, 0)
    deg = B.sum(axis=1)
    pairs = [(deg[i], deg[j]) for i in range(len(deg)) for j in range(i + 1, len(deg)) if B[i, j] > 0]
    if len(pairs) < 2:
        return float("nan")
    x, y = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
    both_x, both_y = np.concatenate([x, y]), np.concatenate([y, x])
    if both_x.std() == 0 or both_y.std() == 0:
        return float("nan")
    return float(np.corrcoef(both_x, both_y)[0, 1])


# ---------------------------------------------------------------- main

def main() -> int:
    companies = [r for r in read(HERE / "packaged_software_companies.csv") if r["ticker"]]
    nodes = sorted({c["ticker"] for c in companies})
    universe = set(nodes)
    name_of = {c["ticker"]: c["name"] for c in companies}
    cik_of = {c["ticker"]: c["cik"].zfill(10) for c in companies}
    print(f"universe: {len(nodes)} companies")

    tickers_corr, corr = return_correlations(universe)
    print(f"return correlations computed for {len(tickers_corr)} companies "
          f"with at least {MIN_OVERLAP_DAYS} overlapping days")
    for th in CORR_THRESHOLDS:
        e = layer_corr(tickers_corr, corr, th)
        possible = len(tickers_corr) * (len(tickers_corr) - 1) / 2
        print(f"  correlation >= {th}: {len(e)} edges, density {len(e)/possible:.3f}")

    auditor_rows = read(OUT / "company_auditors.csv")
    award_rows = [r for r in read(OUT / "contract_awards.csv")
                  if r.get("exact_name_match") in ("True", "true", "1")]
    # contract_awards carries company_name, not ticker: map it back
    ticker_by_name = {c["name"]: c["ticker"] for c in companies}
    for r in award_rows:
        r["ticker"] = ticker_by_name.get(r.get("company_name", ""), "")

    layers = {
        "news_comention": layer_news(universe),
        "tenk_mention": layer_tenk(universe),
        "return_corr": layer_corr(tickers_corr, corr, CORR_EDGE_THRESHOLD),
        "shared_auditor": layer_shared_attribute(auditor_rows, "auditor_normalized", "ticker", universe)
                          or layer_shared_attribute(auditor_rows, "auditor", "ticker", universe),
        "shared_agency": layer_shared_attribute(award_rows, "awarding_agency", "ticker", universe),
        "common_ownership_13f": layer_common_ownership(universe),
    }

    edge_rows, company_rows, network_rows = [], [], []
    per_layer_rank: dict[str, dict[str, float]] = {}

    for layer, edges in layers.items():
        A = adjacency(nodes, edges)
        B = (A > 0).astype(float)
        deg = B.sum(axis=1)
        strength = A.sum(axis=1)
        eig = eigenvector_centrality(A)
        pr = pagerank(A)
        clus = local_clustering(A)
        core = k_core(A)
        btw = betweenness(A)
        icm = icm_influence(A)
        comps = components(A)
        possible = len(nodes) * (len(nodes) - 1) / 2

        for (a, b), w in sorted(edges.items()):
            edge_rows.append({"layer": layer, "company_a": a, "company_b": b, "weight": round(w, 6)})

        for i, t in enumerate(nodes):
            company_rows.append({
                "cik": cik_of[t], "ticker": t, "name": name_of[t], "layer": layer,
                "degree": int(deg[i]), "strength": round(float(strength[i]), 4),
                "eigenvector_centrality": round(float(eig[i]), 6),
                "pagerank": round(float(pr[i]), 6),
                "clustering": round(float(clus[i]), 4),
                "k_core": int(core[i]),
                "betweenness": round(float(btw[i]), 6),
                "icm_influence_companies_reached": round(float(icm[i]), 3),
                "layers_with_an_edge": "",
            })
        # Rank within the layer so layers with different scales can be combined. A company
        # with no edge in this layer gets 0 rather than an arbitrary position among the
        # zero-centrality ties, which previously put unconnected companies mid-table.
        ranks = {}
        connected = [(eig[i], t) for i, t in enumerate(nodes) if deg[i] > 0]
        connected.sort()
        for position, (_, t) in enumerate(connected):
            ranks[t] = (position + 1) / len(connected) if connected else 0.0
        per_layer_rank[layer] = {t: ranks.get(t, 0.0) for t in nodes}

        network_rows.append({
            "layer": layer,
            "nodes_with_an_edge": int((deg > 0).sum()),
            "edges": len(edges),
            "density": round(len(edges) / possible, 4),
            "mean_degree": round(float(deg.mean()), 2),
            "max_degree": int(deg.max()) if len(deg) else 0,
            "mean_clustering": round(float(clus.mean()), 4),
            "components_with_edges": sum(1 for c in comps if len(c) > 1),
            "largest_component": len(comps[0]) if comps else 0,
            "degree_assortativity": round(assortativity(A), 4) if len(edges) > 1 else "",
            "mean_icm_reach": round(float(icm.mean()), 3),
        })
        print(f"{layer:16} edges {len(edges):>6} | density {len(edges)/possible:.4f} | "
              f"largest component {len(comps[0]) if comps else 0:>3} | mean ICM reach {icm.mean():.2f}")

    # Composite: mean of the per-layer eigenvector ranks, so no single layer dominates
    composite = {t: round(float(np.mean([per_layer_rank[l][t] for l in layers])), 4) for t in nodes}
    layers_present = {t: sum(1 for l in layers if per_layer_rank[l][t] > 0) for t in nodes}
    for t in nodes:
        company_rows.append({
            "cik": cik_of[t], "ticker": t, "name": name_of[t], "layer": "COMPOSITE",
            "degree": "", "strength": "", "eigenvector_centrality": composite[t],
            "pagerank": "", "clustering": "", "k_core": "", "betweenness": "",
            "icm_influence_companies_reached": "",
            "layers_with_an_edge": layers_present[t],
        })

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "connectedness_edges.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["layer", "company_a", "company_b", "weight"])
        w.writeheader()
        w.writerows(edge_rows)
    with (OUT / "connectedness_by_company.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(company_rows[0].keys()))
        w.writeheader()
        w.writerows(company_rows)
    with (OUT / "connectedness_network.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(network_rows[0].keys()))
        w.writeheader()
        w.writerows(network_rows)

    top = sorted(composite.items(), key=lambda kv: -kv[1])[:10]
    print("\nmost connected by composite rank (mean of per-layer eigenvector ranks):")
    for t, v in top:
        print(f"  {t:6} {v:.3f}  layers={layers_present[t]}/5  {name_of[t][:38]}")
    import collections as _collections
    spread = dict(sorted(_collections.Counter(layers_present.values()).items()))
    print(f"companies by number of layers they appear in: {spread}")
    isolated = [t for t in nodes if layers_present[t] == 0]
    if isolated:
        print(f"companies with no edge in any layer ({len(isolated)}): {isolated[:10]}")
    print(f"\nWrote {len(edge_rows)} edges, {len(company_rows)} company-layer rows, "
          f"{len(network_rows)} layer summaries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

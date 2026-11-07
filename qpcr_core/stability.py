"""Stability of reference genes: geNorm (Vandesompele et al. 2002) and NormFinder (Andersen et al. 2004).

Both work on one matrix: samples × genes of log2 relative quantities.
"""

from __future__ import annotations

import math

import numpy as np

V_CUTOFF = 0.15  # Vandesompele 2002: a further reference gene adds little below this


def log2_quantities(
    mean_cq: dict[tuple[str, str], float | None],
    eff: dict[str, float],
    samples: list[str],
    genes: list[str],
) -> tuple[np.ndarray, tuple[str, ...], tuple[str, ...]]:
    """log2 Q = (min Cq − Cq) · log2(1 + E); a sample without a Cq of any gene is left out."""
    kept = [s for s in samples if all(mean_cq.get((s, g)) is not None for g in genes)]
    excluded = tuple(s for s in samples if s not in kept)
    cq = np.array([[mean_cq[(s, g)] for g in genes] for s in kept], dtype=float).reshape(len(kept), len(genes))
    scale = np.array([math.log2(1.0 + eff.get(g, 1.0)) for g in genes])
    x = (cq.min(axis=0) - cq) * scale if kept else cq
    return x, tuple(kept), excluded


def genorm_m(log2q: np.ndarray) -> np.ndarray:
    """M of each gene: the mean SD of its log2 ratios with every other gene."""
    n, k = log2q.shape
    if k < 2 or n < 3:
        raise ValueError("geNorm needs at least 2 genes and 3 samples")
    diffs = log2q[:, :, None] - log2q[:, None, :]
    v = diffs.std(axis=0, ddof=1)
    return v.sum(axis=1) / (k - 1)


def genorm_ranking(
    log2q: np.ndarray, genes: list[str]
) -> tuple[tuple[str, ...], tuple[tuple[tuple[str, ...], float], ...]]:
    """Exclude the least stable gene step by step; the last two share the first place."""
    remaining = list(genes)
    removed: list[str] = []
    steps: list[tuple[tuple[str, ...], float]] = []
    while True:
        cols = [genes.index(g) for g in remaining]
        m = genorm_m(log2q[:, cols])
        steps.append((tuple(remaining), float(m.mean())))
        if len(remaining) == 2:
            break
        worst = max(range(len(remaining)), key=lambda i: (round(float(m[i]), 12), remaining[i]))
        removed.append(remaining.pop(worst))
    return tuple(sorted(remaining)) + tuple(reversed(removed)), tuple(steps)


def pairwise_v(log2q: np.ndarray, genes: list[str], ranking: tuple[str, ...]) -> dict[int, float]:
    """V(n/n+1): the SD of log2 of the ratio of normalization factors from the n and n+1 best genes."""
    order = [genes.index(g) for g in ranking]
    out: dict[int, float] = {}
    for n in range(2, len(ranking)):
        nf_n = log2q[:, order[:n]].mean(axis=1)
        nf_n1 = log2q[:, order[: n + 1]].mean(axis=1)
        out[n] = float(np.std(nf_n - nf_n1, ddof=1))
    return out


def recommend(ranking: tuple[str, ...], v: dict[int, float], cutoff: float = V_CUTOFF) -> tuple[tuple[str, ...], bool]:
    """The fewest best genes (at least two) after which one more changes the factor by less than the cutoff."""
    for n in sorted(v):
        if v[n] < cutoff:
            return ranking[:n], True
    if not v:
        return ranking[:2], True
    return ranking, False

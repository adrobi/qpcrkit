"""Stability of reference genes: geNorm (Vandesompele et al. 2002) and NormFinder (Andersen et al. 2004).

Both work on one matrix: samples × genes of log2 relative quantities.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import numpy as np

from .flags import Flag
from .models import Project

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


@dataclass(frozen=True)
class NormFinderResult:
    rho: np.ndarray  # per gene, lower is more stable
    d: np.ndarray  # shrunken shifts, groups × genes; without groups zeros, 1 × genes
    v: np.ndarray  # their variances; without groups the intragroup variance itself, 1 × genes
    groups_used: int  # 0: groups not taken into account
    notes: tuple[str, ...]


def _intragroup_variance(x: np.ndarray) -> np.ndarray:
    """Per gene, corrected for the number of genes; x is one group, samples × genes."""
    n, k = x.shape
    resid = x - x.mean(axis=0) - x.mean(axis=1, keepdims=True) + x.mean()
    a = (resid**2).sum(axis=0) / (n - 1)
    return np.maximum((a - a.sum() / (k * (k - 1))) / (1 - 2 / k), 0.0)


def normfinder(log2q: np.ndarray, groups: list[str]) -> NormFinderResult:
    """NormFinder rho, as NormqPCR's stabMeasureRho; "" is a sample without a group."""
    n, k = log2q.shape
    if k < 3:
        raise ValueError("NormFinder needs at least 3 genes")
    sizes = {g: groups.count(g) for g in dict.fromkeys(groups) if g}
    usable = [g for g, size in sizes.items() if size >= 2]
    if len(usable) < 2:  # every sample is used, so nothing is "left out"
        sigma2 = _intragroup_variance(log2q)
        return NormFinderResult(np.sqrt(sigma2), np.zeros((1, k)), sigma2[None, :], 0, ("no_groups",))
    notes: list[str] = []
    if any(not g for g in groups):
        notes.append("ungrouped_samples")
    if any(size < 2 for size in sizes.values()):
        notes.append("small_groups")

    blocks = [log2q[[i for i, g in enumerate(groups) if g == name]] for name in usable]
    sizes_used = np.array([len(b) for b in blocks], dtype=float)
    y = np.array([b.mean(axis=0) for b in blocks])  # group means, groups × genes
    va = np.array([_intragroup_variance(b) for b in blocks]) / sizes_used[:, None]
    m = len(blocks)
    d = y - y.mean(axis=1, keepdims=True) - y.mean(axis=0, keepdims=True) + y.mean()  # unweighted by group size
    gamma2 = max(float((d**2).sum() / ((m - 1) * (k - 1)) - va.mean()), 0.0)
    total = gamma2 + va
    with np.errstate(invalid="ignore", divide="ignore"):
        shrink = np.where(total > 0, gamma2 / total, 0.0)
    d_new = d * shrink
    v_new = va + va * shrink
    rho = (np.abs(d_new) + np.sqrt(v_new)).mean(axis=0)
    return NormFinderResult(rho, d_new, v_new, m, tuple(notes))


def normfinder_best_pair(result: NormFinderResult, genes: list[str]) -> tuple[tuple[str, str], float]:
    """The pair whose average is most stable (Andersen 2004, combination of two genes)."""
    best: tuple[float, tuple[str, str]] | None = None
    for a, b in itertools.combinations(range(len(genes)), 2):
        d = (result.d[:, a] + result.d[:, b]) / 2
        v = (result.v[:, a] + result.v[:, b]) / 4
        rho = float((np.abs(d) + np.sqrt(v)).mean())
        if best is None or rho < best[0]:
            best = (rho, (genes[a], genes[b]))
    if best is None:
        raise ValueError("a pair needs at least 2 genes")
    return best[1], best[0]



# --- one project ---


@dataclass(frozen=True)
class StabilityResult:
    candidates: tuple[str, ...]  # geNorm ranking, best first; as chosen when geNorm was not computed
    samples: tuple[str, ...]
    excluded_samples: tuple[str, ...]
    genorm_m: dict[str, float]
    genorm_steps: tuple[tuple[tuple[str, ...], float], ...]
    pairwise_v: dict[int, float]
    recommended: tuple[str, ...]
    normfinder_rho: dict[str, float]
    best_pair: tuple[str, str] | None
    best_pair_rho: float | None
    groups_used: int
    notes: tuple[str, ...]


def stability_candidates(project: Project) -> list[str]:
    """Targets marked as candidates; by default the references, or every target when there is none."""
    targets = project.targets
    references = {n for n, t in targets.items() if t.kind == "reference"}
    default = references or set(targets)
    chosen = [n for n, t in targets.items() if t.stability_candidate or (t.stability_candidate is None and n in default)]
    return sorted(chosen)


def _group_of(project: Project, sample: str) -> str:
    known = project.samples.get(sample)
    return (known.group or "").strip() if known else ""


def analyze_stability(
    project: Project, mean_cq: dict[tuple[str, str], float | None], eff: dict[str, float]
) -> tuple[StabilityResult | None, list[Flag]]:
    """The ranking of the candidates; what cannot be computed stays empty and is named in the notes."""
    genes = stability_candidates(project)
    if not genes:
        return None, []
    samples = sorted({s for (s, t) in mean_cq if t in genes})
    x, kept, excluded = log2_quantities(mean_cq, eff, samples, genes)
    flags = [Flag("info", "stability_samples_excluded", {"count": len(excluded)})] if excluded and len(genes) >= 2 else []
    notes: list[str] = []
    ranking: tuple[str, ...] = tuple(genes)
    m: dict[str, float] = {}
    steps: tuple = ()
    v: dict[int, float] = {}
    recommended: tuple[str, ...] = ()
    rho: dict[str, float] = {}
    pair: tuple[str, str] | None = None
    pair_rho: float | None = None
    groups_used = 0
    if len(genes) < 2:
        notes.append("few_candidates")
    elif len(kept) < 3:
        notes.append("few_samples")
    else:
        m = {g: float(value) for g, value in zip(genes, genorm_m(x))}
        ranking, steps = genorm_ranking(x, genes)
        v = pairwise_v(x, genes, ranking)
        recommended, found = recommend(ranking, v)
        if not found:
            notes.append("v_never_below")
        if len(genes) >= 3:
            nf = normfinder(x, [_group_of(project, s) for s in kept])
            rho = {g: float(value) for g, value in zip(genes, nf.rho)}
            pair, pair_rho = normfinder_best_pair(nf, genes)
            groups_used = nf.groups_used
            notes += nf.notes
        else:
            notes.append("few_candidates_normfinder")
    result = StabilityResult(
        ranking, kept, excluded, m, steps, v, recommended, rho, pair, pair_rho, groups_used, tuple(notes)
    )
    return result, flags


def reference_flags(project: Project, mean_cq: dict[tuple[str, str], float | None], eff: dict[str, float]) -> list[Flag]:
    """Are the chosen references stable in this experiment? Judged by geNorm M among themselves."""
    references = sorted(n for n, t in project.targets.items() if t.kind == "reference")
    if len(references) == 1:
        return [Flag("info", "single_reference", target=references[0])]
    if len(references) < 2:
        return []
    samples = sorted({s for (s, t) in mean_cq if t in references})
    x, kept, _ = log2_quantities(mean_cq, eff, samples, references)
    if len(kept) < 3:
        return []
    limit = project.settings.genorm_m_max
    return [
        Flag("warning", "reference_unstable", {"m": float(value), "limit": limit}, target=name)
        for name, value in zip(references, genorm_m(x))
        if value > limit
    ]

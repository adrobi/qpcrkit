"""Inter-run calibration (qbase style, Hellemans et al. 2007).

CF(run) = mean IRC Cq on that run − mean of per-run IRC means; calibrated Cq = Cq − CF.
Gene-specific IRCs are used when present on every run, otherwise all IRCs together.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import fmean

from .flags import Flag
from .models import Project


def _factors(per_run: dict[str, list[float]]) -> dict[str, float]:
    means = {run_id: fmean(v) for run_id, v in per_run.items()}
    grand = fmean(means.values())
    return {run_id: m - grand for run_id, m in means.items()}


def calibration_factors(project: Project) -> tuple[dict[tuple[str, str], float], list[Flag]]:
    if len(project.runs) <= 1:
        return {}, []
    by_target: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    all_irc: dict[str, list[float]] = defaultdict(list)
    targets: set[str] = set()
    for run, _well, rxn in project.iter_reactions():
        targets.add(rxn.target)
        if rxn.role == "irc" and not rxn.excluded and rxn.cq is not None:
            by_target[rxn.target][run.id].append(rxn.cq)
            all_irc[run.id].append(rxn.cq)

    if not all_irc:
        return {}, [Flag("info", "no_irc")]

    flags = [Flag("warning", "irc_missing", run_id=r.id) for r in project.runs if r.id not in all_irc]
    run_ids = {r.id for r in project.runs}
    general = _factors(all_irc)
    factors: dict[tuple[str, str], float] = {}
    for target in sorted(targets):
        own = by_target.get(target, {})
        per_run = _factors(own) if set(own) == run_ids else general
        for run_id, cf in per_run.items():
            factors[(run_id, target)] = cf
    return factors, flags


def corrected_cq(factors: dict[tuple[str, str], float], run_id: str, target: str, cq: float) -> float:
    return cq - factors.get((run_id, target), 0.0)

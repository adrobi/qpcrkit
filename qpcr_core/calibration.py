"""Inter-run calibration (qbase style, Hellemans et al. 2007).

Each IRC is a (sample, target) pair measured on several runs. For an IRC k present on every
run that has IRCs, the deviation of run r is mean_{r,k} − mean over runs of mean_{·,k}; the
calibration factor CF(run) averages those deviations, and calibrated Cq = Cq − CF.
A target uses its own IRCs when they cover every IRC run, otherwise all common IRCs.
Only runs without any IRC get CF = 0 (flag ``irc_missing``).
"""

from __future__ import annotations

from collections import defaultdict
from statistics import fmean

from .flags import Flag
from .models import Project


def _factors(irc: dict[tuple[str, str], dict[str, float]], keys: list[tuple[str, str]], runs: list[str]) -> dict[str, float]:
    deviations: dict[str, list[float]] = defaultdict(list)
    for k in keys:
        grand = fmean(irc[k][r] for r in runs)
        for r in runs:
            deviations[r].append(irc[k][r] - grand)
    return {r: fmean(v) for r, v in deviations.items()}


def calibration_factors(project: Project) -> tuple[dict[tuple[str, str], float], list[Flag]]:
    if len(project.runs) <= 1:
        return {}, []
    values: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    targets: set[str] = set()
    for run, well, rxn in project.iter_reactions():
        targets.add(rxn.target)
        if rxn.role == "irc" and not rxn.excluded and rxn.cq is not None:
            values[(well.sample or "", rxn.target)][run.id].append(rxn.cq)

    if not values:
        return {}, [Flag("info", "no_irc")]

    irc = {k: {r: fmean(v) for r, v in per_run.items()} for k, per_run in values.items()}
    irc_runs = [r.id for r in project.runs if any(r.id in m for m in irc.values())]
    flags = [Flag("warning", "irc_missing", run_id=r.id) for r in project.runs if r.id not in irc_runs]
    common = sorted(k for k, m in irc.items() if all(r in m for r in irc_runs))
    if len(irc_runs) < 2 or not common:
        if len(irc_runs) >= 2:
            flags.append(Flag("warning", "irc_no_common"))
        return {}, flags

    general = _factors(irc, common, irc_runs)
    factors: dict[tuple[str, str], float] = {}
    for target in sorted(targets):
        own = [k for k in common if k[1] == target]
        if not own and any(k[1] == target for k in irc):
            flags.append(Flag("warning", "irc_partial", target=target))
        per_run = _factors(irc, own, irc_runs) if own else general
        for run_id, cf in per_run.items():
            factors[(run_id, target)] = cf
    return factors, flags


def corrected_cq(factors: dict[tuple[str, str], float], run_id: str, target: str, cq: float) -> float:
    return cq - factors.get((run_id, target), 0.0)

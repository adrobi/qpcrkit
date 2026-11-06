"""Reaction-level QC: technical replicate spread, outlier suggestions, controls."""

from __future__ import annotations

import statistics
from collections import defaultdict

from .flags import Flag
from .models import Project
from .stdcurve import CqFn


def check_reactions(project: Project, cq_of: CqFn | None = None) -> list[Flag]:
    """``cq_of`` gives the Cq to judge; by default the instrument's."""
    s = project.settings
    flags: list[Flag] = []
    # key -> list of (coord, cq or None)
    groups: dict[tuple, list[tuple[str, float | None]]] = defaultdict(list)
    nrt: list[tuple[str, str, str | None, str, float]] = []
    unnamed: set[tuple[str, str]] = set()

    for run, well, rxn in project.iter_reactions():
        if rxn.excluded:
            continue
        cq = rxn.cq if cq_of is None else cq_of(run, well, rxn)
        if rxn.role == "ntc":
            if cq is not None and cq < s.ntc_cq_min:
                flags.append(Flag("error", "ntc_contamination", {"cq": cq}, run.id, (well.coord,), rxn.target, well.sample))
            continue
        if rxn.role == "unknown" and cq is not None and cq >= s.late_cq:
            flags.append(Flag("info", "late_amplification", {"cq": cq}, run.id, (well.coord,), rxn.target, well.sample))
        if rxn.role == "nrt":
            if cq is not None:
                nrt.append((run.id, rxn.target, well.sample, well.coord, cq))
            continue
        if rxn.role == "std":
            if rxn.quantity is None:  # no level to group by
                continue
            key = (run.id, rxn.target, "std", None, rxn.quantity)
        elif rxn.role == "unknown" and not well.sample:  # unnamed wells are not replicates of each other
            unnamed.add((run.id, well.coord))
            continue
        else:
            key = (run.id, rxn.target, rxn.role, well.sample, None)
        groups[key].append((well.coord, cq))

    if unnamed:
        flags.append(Flag("info", "wells_without_sample", {"count": len(unnamed)}))

    for (run_id, target, _role, sample, _q), reps in groups.items():
        values = [cq for _, cq in reps if cq is not None]
        coords = tuple(c for c, _ in reps)
        if values and len(values) < len(reps):
            flags.append(Flag("warning", "partial_undetermined", {}, run_id, coords, target, sample))
        if len(values) < 2:
            continue
        sd = statistics.stdev(values)
        if sd > s.rep_sd_max:
            flags.append(Flag("warning", "rep_sd_high", {"sd": sd, "limit": s.rep_sd_max}, run_id, coords, target, sample))
        if len(values) >= 3:
            median = statistics.median(values)
            coord, cq = max(((c, v) for c, v in reps if v is not None), key=lambda cv: abs(cv[1] - median))
            if abs(cq - median) > 2 * s.rep_sd_max:
                flags.append(
                    Flag("warning", "outlier_suggested", {"cq": cq, "median": median}, run_id, (coord,), target, sample)
                )
    for run_id, target, sample, coord, cq in nrt:
        values = [v for _, v in groups.get((run_id, target, "unknown", sample, None), []) if v is not None]
        if not values or cq - statistics.fmean(values) < s.nrt_min_delta:
            flags.append(
                Flag("warning", "nrt_amplified", {"cq": cq, "delta": s.nrt_min_delta}, run_id, (coord,), target, sample)
            )
    return flags

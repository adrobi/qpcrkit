"""Reaction-level QC: technical replicate spread, outlier suggestions, controls."""

from __future__ import annotations

import statistics
from collections import defaultdict

from .flags import Flag
from .models import Project


def check_reactions(project: Project) -> list[Flag]:
    s = project.settings
    flags: list[Flag] = []
    # key -> list of (coord, cq or None)
    groups: dict[tuple, list[tuple[str, float | None]]] = defaultdict(list)

    for run, well, rxn in project.iter_reactions():
        if rxn.excluded:
            continue
        if rxn.role == "ntc":
            if rxn.cq is not None and rxn.cq < s.ntc_cq_min:
                flags.append(Flag("error", "ntc_contamination", {"cq": rxn.cq}, run.id, (well.coord,), rxn.target, well.sample))
            continue
        if rxn.role == "unknown" and rxn.cq is not None and rxn.cq >= s.late_cq:
            flags.append(Flag("info", "late_amplification", {"cq": rxn.cq}, run.id, (well.coord,), rxn.target, well.sample))
        if rxn.role == "std":
            key = (run.id, rxn.target, None, rxn.quantity)
        else:
            key = (run.id, rxn.target, well.sample, None)
        groups[key].append((well.coord, rxn.cq))

    for (run_id, target, sample, _q), reps in groups.items():
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
    return flags

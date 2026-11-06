"""Relative quantification, generalized Pfaffl / qbase formula.

RQ_t(s) = A_t^ΔCq_t(s) / geomean_ref(A_ref^ΔCq_ref(s)),  ΔCq = Cq(calibrator) − Cq(s),  A = 1 + E.
With E = 1.0 for every target this is exactly 2^−ΔΔCt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean

from .curves import USABLE_EFFICIENCY
from .flags import Flag
from .models import Project
from .stdcurve import StdCurve


@dataclass
class SampleRQ:
    sample: str
    group: str
    target: str
    mean_cq: float
    delta_cq: float
    rq: float
    log2_rq: float




def efficiencies_with_source(
    project: Project, curves: dict[tuple[str | None, str], StdCurve]
) -> tuple[dict[str, float], dict[str, str], list[Flag]]:
    """Efficiency per target, where it came from (stdcurve | manual | ideal), and flags."""
    eff: dict[str, float] = {}
    source: dict[str, str] = {}
    flags: list[Flag] = []
    lo, hi = USABLE_EFFICIENCY
    for name, t in project.targets.items():
        own = [c.efficiency for (_run, target), c in curves.items() if target == name]
        if t.efficiency_mode == "stdcurve" and own:
            if lo <= fmean(own) <= hi:
                eff[name], source[name] = fmean(own), "stdcurve"
                continue
            flags.append(Flag("warning", "efficiency_unusable", {"eff": fmean(own)}, target=name))
        if t.efficiency_mode != "ideal" and t.efficiency_manual is not None:
            eff[name], source[name] = t.efficiency_manual, "manual"
        else:
            eff[name], source[name] = 1.0, "ideal"
    return eff, source, flags


def efficiencies(project: Project, curves: dict[tuple[str | None, str], StdCurve]) -> dict[str, float]:
    return efficiencies_with_source(project, curves)[0]


def _calibrator_cq(project: Project, mean_cq: dict[tuple[str, str], float | None], target: str) -> float | None:
    s = project.settings
    if s.calibrator_sample:
        return mean_cq.get((s.calibrator_sample, target))
    values = [
        v
        for name, smp in project.samples.items()
        if smp.group == s.control_group and (v := mean_cq.get((name, target))) is not None
    ]
    return fmean(values) if values else None


def relative_quantities(
    project: Project, mean_cq: dict[tuple[str, str], float | None], eff: dict[str, float]
) -> tuple[list[SampleRQ], list[Flag]]:
    s = project.settings
    if not (s.control_group or s.calibrator_sample):
        return [], [Flag("error", "no_control")]
    refs = sorted(n for n, t in project.targets.items() if t.kind == "reference")
    if not refs:
        return [], [Flag("error", "no_reference_targets")]
    targets = sorted(n for n, t in project.targets.items() if t.kind == "target")

    flags: list[Flag] = []
    cal = {t: _calibrator_cq(project, mean_cq, t) for t in refs + targets}
    for t in refs + targets:
        if cal[t] is None:
            flags.append(Flag("error", "no_calibrator_cq", target=t))
    usable_refs = [r for r in refs if cal[r] is not None]
    ungrouped = {
        s for s, _t in mean_cq if not (project.samples.get(s) and project.samples[s].group)
    }
    if ungrouped:
        flags.append(Flag("warning", "samples_without_group", {"count": len(ungrouped)}))

    def amp(t: str) -> float:
        return 1.0 + eff.get(t, 1.0)

    rqs: list[SampleRQ] = []
    for name, smp in sorted(project.samples.items()):
        if not smp.group:
            continue
        log_norm = [
            (cal[r] - cq) * math.log(amp(r))
            for r in usable_refs
            if (cq := mean_cq.get((name, r))) is not None
        ]
        if not log_norm:
            flags.append(Flag("error", "no_reference_for_sample", sample=name))
            continue
        if len(log_norm) < len(usable_refs):
            flags.append(Flag("warning", "partial_reference", sample=name))
        norm = fmean(log_norm)  # log of the geometric mean
        for t in targets:
            if cal[t] is None:
                continue
            cq = mean_cq.get((name, t))
            if cq is None:
                flags.append(Flag("info", "no_cq", target=t, sample=name))
                continue
            delta = cal[t] - cq
            ln_rq = delta * math.log(amp(t)) - norm
            rqs.append(SampleRQ(name, smp.group, t, cq, delta, math.exp(ln_rq), ln_rq / math.log(2)))
    return rqs, flags

"""Relative quantification, generalized Pfaffl / qbase formula.

RQ_t(s) = A_t^ΔCq_t(s) / geomean_ref(A_ref^ΔCq_ref(s)),  ΔCq = Cq(calibrator) − Cq(s),  A = 1 + E.
With E = 1.0 for every target this is exactly 2^−ΔΔCt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean

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


def efficiencies(project: Project, curves: dict[tuple[str | None, str], StdCurve]) -> dict[str, float]:
    out: dict[str, float] = {}
    for name, t in project.targets.items():
        own = [c.efficiency for (_run, target), c in curves.items() if target == name]
        if t.efficiency_mode == "ideal":
            out[name] = 1.0
        elif t.efficiency_mode == "stdcurve" and own:
            out[name] = fmean(own)
        else:
            out[name] = t.efficiency_manual if t.efficiency_manual is not None else 1.0
    return out


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
    for t in targets:
        if cal[t] is None:
            flags.append(Flag("error", "no_calibrator_cq", target=t))

    def amp(t: str) -> float:
        return 1.0 + eff.get(t, 1.0)

    rqs: list[SampleRQ] = []
    for name, smp in sorted(project.samples.items()):
        if not smp.group:
            continue
        log_norm = [
            (cal[r] - cq) * math.log(amp(r))
            for r in refs
            if cal[r] is not None and (cq := mean_cq.get((name, r))) is not None
        ]
        if not log_norm:
            flags.append(Flag("error", "no_reference_for_sample", sample=name))
            continue
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

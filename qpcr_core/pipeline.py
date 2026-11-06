"""The one place that chains the analysis steps: analyze(project) -> Results."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import fmean

from .calibration import calibration_factors, corrected_cq
from .curves import (
    CurveKey,
    CurveResult,
    analyze_curves,
    curve_flags,
    run_uses_calculated,
    source_flags,
    target_efficiencies,
)
from .flags import Flag
from .models import Project, Reaction, Run, Well
from .qc import check_reactions
from .relquant import SampleRQ, efficiencies_with_source, relative_quantities
from .stats import Comparison, GroupSummary, compare, summarize
from .stdcurve import StdCurve, fit_std_curves, quantify


@dataclass
class QuantRow:
    run_id: str
    sample: str
    target: str
    mean_cq: float
    quantity: float
    extrapolated: bool


@dataclass
class Results:
    flags: list[Flag]
    calibration: dict[tuple[str, str], float]
    std_curves: dict[tuple[str | None, str], StdCurve]
    efficiencies: dict[str, float]
    efficiency_source: dict[str, str]  # stdcurve | curves | manual | ideal
    mean_cq: dict[tuple[str, str], float | None]
    quantities: list[QuantRow]
    rqs: list[SampleRQ]
    groups: list[GroupSummary]
    comparisons: list[Comparison]
    curves: dict[CurveKey, CurveResult] = field(default_factory=dict)
    curve_efficiency: dict[str, float] = field(default_factory=dict)  # shown whatever efficiency_mode is

    def flags_by_severity(self, severity: str) -> list[Flag]:
        return [f for f in self.flags if f.severity == severity]


def analyze(project: Project) -> Results:
    curve_results, flags = analyze_curves(project)
    calculated = {run.id: run_uses_calculated(run, project.settings) for run in project.runs}

    def raw_cq_of(run: Run, well: Well, rxn: Reaction) -> float | None:
        if rxn.excluded:
            return None
        if not calculated[run.id]:
            return rxn.cq
        result = curve_results.get((run.id, well.coord, rxn.target, rxn.fluor))
        return result.cq_calc if result else None

    flags += check_reactions(project, raw_cq_of)
    factors, cal_flags = calibration_factors(project, raw_cq_of)
    flags += cal_flags
    flags += source_flags(project, curve_results, factors)
    flags += curve_flags(project, curve_results, raw_cq_of)

    def cq_of(run: Run, well: Well, rxn: Reaction) -> float | None:
        cq = raw_cq_of(run, well, rxn)
        return None if cq is None else corrected_cq(factors, run.id, rxn.target, cq)

    std_curves, std_flags = fit_std_curves(project, cq_of)
    flags += std_flags

    per_run: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    per_sample: dict[tuple[str, str], list[float]] = defaultdict(list)
    for run, well, rxn in project.iter_reactions():
        if rxn.role != "unknown" or not well.sample or rxn.excluded:
            continue
        per_sample.setdefault((well.sample, rxn.target), [])
        cq = cq_of(run, well, rxn)
        if cq is not None:
            per_run[(run.id, well.sample, rxn.target)].append(cq)
            per_sample[(well.sample, rxn.target)].append(cq)
    mean_cq = {k: (fmean(v) if v else None) for k, v in per_sample.items()}

    pooled = project.settings.pool_std_runs
    quantities: list[QuantRow] = []
    for (run_id, sample, target), values in per_run.items():
        curve = std_curves.get((None if pooled else run_id, target))
        if curve is None:
            continue
        cq = fmean(values)
        q, extra = quantify(curve, cq)
        quantities.append(QuantRow(run_id, sample, target, cq, q, extra))
        if extra:
            flags.append(Flag("warning", "extrapolated", {"quantity": q}, run_id, target=target, sample=sample))

    eff, eff_source, eff_flags = efficiencies_with_source(project, std_curves, curve_results)
    flags += eff_flags
    rqs, rq_flags = relative_quantities(project, mean_cq, eff)
    flags += rq_flags
    comparisons, stat_flags = compare(rqs, project.settings.control_group, project.settings.test)
    flags += stat_flags

    return Results(
        flags=flags,
        calibration=factors,
        std_curves=std_curves,
        efficiencies=eff,
        efficiency_source=eff_source,
        mean_cq=mean_cq,
        quantities=quantities,
        rqs=rqs,
        groups=summarize(rqs),
        comparisons=comparisons,
        curves=curve_results,
        curve_efficiency=target_efficiencies(project, curve_results),
    )

"""Standard curves: Cq = slope·log10(Q) + intercept, efficiency, absolute quantification."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .flags import Flag
from .models import Project, Reaction, Run

CqFn = Callable[[Run, Reaction], "float | None"]


@dataclass
class StdCurve:
    target: str
    run_id: str | None
    slope: float
    intercept: float
    r2: float
    efficiency: float
    n_points: int
    n_levels: int
    min_q: float
    max_q: float
    lowest_detected: float | None
    points: list[tuple[float, float]]  # (quantity, cq)


def fit_std_curves(project: Project, cq_of: CqFn) -> tuple[dict[tuple[str | None, str], StdCurve], list[Flag]]:
    s = project.settings
    # key -> quantity -> list of cq (None = no amplification)
    data: dict[tuple[str | None, str], dict[float, list[float | None]]] = defaultdict(lambda: defaultdict(list))
    no_quantity: dict[tuple[str, str], list[str]] = defaultdict(list)
    for run, well, rxn in project.iter_reactions():
        if rxn.role != "std" or rxn.excluded:
            continue
        if not rxn.quantity or rxn.quantity <= 0:
            no_quantity[(run.id, rxn.target)].append(well.coord)
            continue
        key = (None if s.pool_std_runs else run.id, rxn.target)
        data[key][rxn.quantity].append(cq_of(run, rxn))

    curves: dict[tuple[str | None, str], StdCurve] = {}
    flags = [
        Flag("warning", "std_no_quantity", {}, run_id, tuple(coords), target)
        for (run_id, target), coords in no_quantity.items()
    ]
    for key, levels in data.items():
        run_id, target = key
        points = [(q, cq) for q, cqs in levels.items() for cq in cqs if cq is not None]
        n_levels = len({q for q, _ in points})
        if n_levels < 3:
            flags.append(Flag("warning", "std_levels_few", {"levels": n_levels}, run_id, target=target))
            continue
        x = np.log10([q for q, _ in points])
        y = np.array([cq for _, cq in points])
        slope, intercept = np.polyfit(x, y, 1)
        r2 = float(np.corrcoef(x, y)[0, 1] ** 2)
        eff = 10 ** (-1 / slope) - 1
        complete = [q for q, cqs in levels.items() if cqs and all(c is not None for c in cqs)]
        curves[key] = StdCurve(
            target=target,
            run_id=run_id,
            slope=float(slope),
            intercept=float(intercept),
            r2=r2,
            efficiency=float(eff),
            n_points=len(points),
            n_levels=n_levels,
            min_q=min(q for q, _ in points),
            max_q=max(q for q, _ in points),
            lowest_detected=min(complete) if complete else None,
            points=sorted(points),
        )
        if not s.eff_min <= eff <= s.eff_max:
            flags.append(Flag("warning", "efficiency_out_of_range", {"eff": float(eff)}, run_id, target=target))
        if r2 < s.r2_min:
            flags.append(Flag("warning", "r2_low", {"r2": r2}, run_id, target=target))
    return curves, flags


def quantify(curve: StdCurve, cq: float) -> tuple[float, bool]:
    q = 10 ** ((cq - curve.intercept) / curve.slope)
    tol = 1e-9 * curve.max_q
    extrapolated = q < curve.min_q * (1 - 1e-9) or q > curve.max_q + tol
    return q, extrapolated

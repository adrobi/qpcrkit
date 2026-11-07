"""Publication figures with matplotlib's object API (no pyplot: safe in GUI and headless)."""

from __future__ import annotations

import math
import os
import re
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from .curves import derivative_curve, subtracted_curve
from .models import Curve, Project, Reaction
from .pipeline import Results
from .stability import V_CUTOFF, StabilityResult
from .stdcurve import StdCurve

_FORMATS = {".svg": "svg", ".pdf": "pdf", ".png": "png"}
BAR_COLOR = "#2563eb"
LINE_COLORS = ("#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#0891b2", "#db2777", "#65a30d")


def safe_name(name: str) -> str:
    """A target name as part of a file name."""
    return re.sub(r"[^\w.+-]+", "_", name, flags=re.UNICODE).strip("_")


def significance_stars(p: float | None) -> str:
    if p is None or math.isnan(p):
        return ""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return ""


def _ink(style: dict | None, default: str) -> str:
    """Lines and dots on a dark background take the text color; exports keep the grays."""
    return (style or {}).get("text.color", default)


def _curve_axes(fig: Figure, by_target: dict[str, list[Curve]], log: bool = False):
    """All curves in one collection per target: hundreds of separate lines would be slow to draw."""
    ax = fig.add_subplot()
    colors = {t: LINE_COLORS[i % len(LINE_COLORS)] for i, t in enumerate(sorted(by_target))}
    for target, curves in by_target.items():
        segments = []
        for c in curves:
            y = np.asarray(c.y, dtype=float)
            segments.append(np.column_stack((c.x, np.where(y > 0, y, np.nan) if log else y)))
        ax.add_collection(LineCollection(segments, colors=colors[target], linewidths=0.8))
    if log:
        ax.set_yscale("log")
    ax.autoscale_view()
    if len(by_target) > 1:
        ax.legend(
            [Line2D([], [], color=colors[t]) for t in sorted(by_target)],
            sorted(by_target),
            fontsize="small",
            frameon=False,
        )
    return ax, colors


def _curves_of(project: Project, run_id: str, target: str | None, pick) -> dict[str, list[Curve]]:
    by_target: dict[str, list[Curve]] = {}
    for run, _well, rxn in project.iter_reactions():
        rxn: Reaction
        if run.id != run_id or rxn.excluded or (target is not None and rxn.target != target):
            continue
        curve = pick(rxn)
        if curve is not None:
            by_target.setdefault(rxn.target, []).append(curve)
    return by_target


def amplification_figure(
    project: Project,
    results: Results,
    run_id: str,
    target: str | None = None,
    log: bool = False,
    threshold: bool = True,
    style: dict | None = None,
) -> Figure:
    with matplotlib.rc_context(style or {}):
        fig = Figure(layout="constrained")
        ax, colors = _curve_axes(fig, _curves_of(project, run_id, target, subtracted_curve), log)
        ax.set_xlabel("Cycle")
        ax.set_ylabel("Signal, background removed")
        ax.set_title(run_id if target is None else f"{run_id}: {target}")
        if threshold:
            levels = {(key[2], r.threshold) for key, r in results.curves.items() if key[0] == run_id and r.threshold}
            for name, value in sorted(levels):
                if name in colors:
                    ax.axhline(value, color=colors[name], ls="--", lw=0.8)
    return fig


def melt_figure(
    project: Project,
    results: Results,
    run_id: str,
    target: str | None = None,
    style: dict | None = None,
) -> Figure:
    with matplotlib.rc_context(style or {}):
        fig = Figure(layout="constrained")
        ax, _ = _curve_axes(fig, _curves_of(project, run_id, target, derivative_curve))
        ax.set_xlabel("Temperature, °C")
        ax.set_ylabel("-dF/dT")
        ax.set_title(run_id if target is None else f"{run_id}: {target}")
    return fig


def std_curve_figure(curve: StdCurve, style: dict | None = None) -> Figure:
    with matplotlib.rc_context(style or {}):
        fig = Figure(layout="constrained")
        ax = fig.add_subplot()
        qs = [p.quantity for p in curve.points]
        ax.scatter(qs, [p.cq for p in curve.points], s=18, color=BAR_COLOR, zorder=3, picker=True, pickradius=5)
        lo, hi = min(qs), max(qs)
        ax.plot([lo, hi], [curve.slope * math.log10(q) + curve.intercept for q in (lo, hi)], color=_ink(style, "0.3"), lw=1)
        ax.set_xscale("log")
        ax.set_xlabel("Quantity")
        ax.set_ylabel("Cq")
        ax.set_title(curve.target)
        ax.text(
            0.97,
            0.95,
            f"E = {curve.efficiency:.1%}\nR² = {curve.r2:.4f}\nslope = {curve.slope:.3f}",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize="small",
        )
    return fig


def expression_figure(
    results: Results, target: str, error: str = "sd", log2: bool = False, style: dict | None = None
) -> Figure:
    groups = [g for g in results.groups if g.target == target]
    comps = [c for c in results.comparisons if c.target == target and c.test != "anova"]
    control = comps[0].group_a if comps else None
    groups.sort(key=lambda g: g.group != control)
    names = [g.group for g in groups]

    with matplotlib.rc_context(style or {}):
        fig = Figure(layout="constrained")
        ax = fig.add_subplot()
        xs = range(len(groups))
        if log2:
            heights = [g.mean_log2 for g in groups]
            errs = [getattr(g, f"{error}_log2") or 0.0 for g in groups]
            yerr = [errs, errs]
        else:
            heights = [g.fold for g in groups]
            bounds = [g.fold_bounds(error) for g in groups]
            yerr = [[h - lo for h, (lo, _) in zip(heights, bounds)], [hi - h for h, (_, hi) in zip(heights, bounds)]]
        ax.bar(xs, heights, color=BAR_COLOR, alpha=0.75, width=0.6)
        ax.errorbar(xs, heights, yerr=yerr, fmt="none", ecolor=_ink(style, "0.2"), capsize=4, lw=1)

        for x, name in zip(xs, names):
            pts = [r.log2_rq if log2 else r.rq for r in results.rqs if r.target == target and r.group == name]
            n = len(pts)
            jitter = [(i - (n - 1) / 2) * 0.08 for i in range(n)]
            ax.scatter([x + j for j in jitter], pts, s=14, color=_ink(style, "0.15"), zorder=3)

        tops = []
        for x, name, h, e in zip(xs, names, heights, yerr[1]):
            pts_max = max((r.log2_rq if log2 else r.rq for r in results.rqs if r.target == target and r.group == name), default=h)
            tops.append(max(h + e, pts_max))
        span = max(tops, default=1.0) - min(0.0, min(heights, default=0.0))
        for x, name, top in zip(xs, names, tops):
            c = next((c for c in comps if c.group_a == control and c.group_b == name), None)
            stars = significance_stars(None if c is None else (c.p_adj if c.p_adj is not None else c.p))
            if stars:
                ax.text(x, top + 0.03 * span, stars, ha="center", va="bottom")
        ax.set_ylim(top=max(tops, default=1.0) + 0.15 * span)

        ax.set_xticks(list(xs), names)
        ax.set_ylabel(f"log2 fold change ({target})" if log2 else f"Fold change ({target})")
        if log2:
            ax.axhline(0, color=_ink(style, "0.5"), lw=0.8)
        ax.set_title(target)
    return fig


def genorm_figure(result: StabilityResult, style: dict | None = None) -> Figure:
    """Mean M while the least stable gene is excluded step by step; beside it V(n/n+1) with the 0.15 line."""
    with matplotlib.rc_context(style or {}):
        fig = Figure(layout="constrained")
        has_v = bool(result.pairwise_v)
        ax = fig.add_subplot(1, 2, 1) if has_v else fig.add_subplot()
        counts = [len(remaining) for remaining, _ in result.genorm_steps]
        ax.plot(range(len(counts)), [m for _, m in result.genorm_steps], marker="o", color=_ink(style, "0.2"), lw=1)
        ax.set_xticks(range(len(counts)), [str(n) for n in counts])
        ax.set_xlabel("Genes left")
        ax.set_ylabel("Mean M")
        ax.set_title("geNorm")
        if has_v:
            vax = fig.add_subplot(1, 2, 2)
            pairs = sorted(result.pairwise_v)
            vax.bar(range(len(pairs)), [result.pairwise_v[n] for n in pairs], color=BAR_COLOR, alpha=0.75, width=0.6)
            vax.axhline(V_CUTOFF, color=_ink(style, "0.3"), ls="--", lw=0.8)
            vax.set_xticks(range(len(pairs)), [f"V{n}/{n + 1}" for n in pairs], rotation=45, ha="right")
            vax.set_ylabel("Pairwise variation V")
    return fig


def normfinder_figure(result: StabilityResult, style: dict | None = None) -> Figure:
    """Stability values, the most stable gene on top."""
    with matplotlib.rc_context(style or {}):
        fig = Figure(layout="constrained")
        ax = fig.add_subplot()
        genes = sorted(result.normfinder_rho, key=result.normfinder_rho.get, reverse=True)
        ax.barh(range(len(genes)), [result.normfinder_rho[g] for g in genes], color=BAR_COLOR, alpha=0.75, height=0.6)
        ax.set_yticks(range(len(genes)), genes)
        ax.set_xlabel("Stability value \u03c1")
        ax.set_title("NormFinder" + ("" if result.groups_used else " (no groups)"))
    return fig


def stability_figure_files(result: StabilityResult | None) -> list[tuple[str, Figure]]:
    """The stability figures worth saving: a method that was not computed has none."""
    if result is None:
        return []
    files = []
    if result.genorm_m:
        files.append(("stability_genorm.svg", genorm_figure(result)))
    if result.normfinder_rho:
        files.append(("stability_normfinder.svg", normfinder_figure(result)))
    return files


def save_figure(fig: Figure, path: str | os.PathLike, width_mm: float = 90, height_mm: float = 70, dpi: int = 300) -> None:
    path = Path(path)
    fmt = _FORMATS.get(path.suffix.lower())
    if fmt is None:
        raise ValueError(f"Unsupported figure format: {path.suffix}")
    fig.set_size_inches(width_mm / 25.4, height_mm / 25.4)
    fig.savefig(path, format=fmt, dpi=dpi)

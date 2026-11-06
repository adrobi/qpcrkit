"""Publication figures with matplotlib's object API (no pyplot: safe in GUI and headless)."""

from __future__ import annotations

import math
import os
import re
from pathlib import Path

import matplotlib
from matplotlib.figure import Figure

from .pipeline import Results
from .stdcurve import StdCurve

_FORMATS = {".svg": "svg", ".pdf": "pdf", ".png": "png"}
BAR_COLOR = "#2563eb"


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


def std_curve_figure(curve: StdCurve, style: dict | None = None) -> Figure:
    with matplotlib.rc_context(style or {}):
        fig = Figure(layout="constrained")
        ax = fig.add_subplot()
        qs = [p.quantity for p in curve.points]
        ax.scatter(qs, [p.cq for p in curve.points], s=18, color=BAR_COLOR, zorder=3)
        lo, hi = min(qs), max(qs)
        ax.plot([lo, hi], [curve.slope * math.log10(q) + curve.intercept for q in (lo, hi)], color="0.3", lw=1)
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
        ax.errorbar(xs, heights, yerr=yerr, fmt="none", ecolor="0.2", capsize=4, lw=1)

        for x, name in zip(xs, names):
            pts = [r.log2_rq if log2 else r.rq for r in results.rqs if r.target == target and r.group == name]
            n = len(pts)
            jitter = [(i - (n - 1) / 2) * 0.08 for i in range(n)]
            ax.scatter([x + j for j in jitter], pts, s=14, color="0.15", zorder=3)

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
            ax.axhline(0, color="0.5", lw=0.8)
        ax.set_title(target)
    return fig


def save_figure(fig: Figure, path: str | os.PathLike, width_mm: float = 90, height_mm: float = 70, dpi: int = 300) -> None:
    path = Path(path)
    fmt = _FORMATS.get(path.suffix.lower())
    if fmt is None:
        raise ValueError(f"Unsupported figure format: {path.suffix}")
    fig.set_size_inches(width_mm / 25.4, height_mm / 25.4)
    fig.savefig(path, format=fmt, dpi=dpi)

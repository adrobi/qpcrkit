"""Generate the deterministic demo in examples/: CFX exports (two plates, IL6 vs GAPDH) and a project with curves."""

from __future__ import annotations

import csv
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUT = Path(__file__).resolve().parent.parent / "examples"
HEADER = ["", "Well", "Fluor", "Target", "Content", "Replicate", "Sample", "Biological Set Name", "Cq",
          "Cq Mean", "Cq Std. Dev", "Starting Quantity (SQ)"]
GAPDH = 19.0
IL6 = {"Ctrl": 28.0, "LPS": 25.0, "LPS+Dex": 27.0}
SLOPE, INTERCEPT = -3.37, 38.0  # IL6 standard curve, E ≈ 98 %


def wells():
    for r in "ABCDEFGH":
        for c in range(1, 13):
            yield f"{r}{c:02d}"


def plate(groups: list[str], shift: float, rng: random.Random, standards: bool) -> list[list[str]]:
    it = wells()
    rows: list[list[str]] = []

    def add(target, content, sample, group, cq, sq=""):
        cq_txt = "NaN" if cq is None else f"{cq:.2f}"
        rows.append([str(len(rows)), next(it), "SYBR", target, content, "", sample, group, cq_txt, "", "", sq])

    for group in groups:
        for b in range(1, 4):
            sample = f"{group}-{b}"
            bio_g, bio_i = rng.gauss(0, 0.15), rng.gauss(0, 0.25)
            for _ in range(3):
                add("GAPDH", "Unkn", sample, group, GAPDH + bio_g + shift + rng.gauss(0, 0.08))
            for _ in range(3):
                add("IL6", "Unkn", sample, group, IL6[group] + bio_i + shift + rng.gauss(0, 0.08))
    for _ in range(2):
        add("GAPDH", "IRC", "IRC", "", 20.0 + shift + rng.gauss(0, 0.05))
        add("IL6", "IRC", "IRC", "", 26.0 + shift + rng.gauss(0, 0.05))
    if standards:
        for q in (1e5, 1e4, 1e3, 1e2, 1e1):
            for _ in range(2):
                add("IL6", "Std", "", "", SLOPE * math.log10(q) + INTERCEPT + shift + rng.gauss(0, 0.1), f"{q:g}")
    add("GAPDH", "NTC", "", "", None)
    add("IL6", "NTC", "", "", None)
    return rows


def demo_project():
    """The exports as a project, with curves that cross the threshold at the Cq of each reaction."""
    from qpcr_core.importers.detect import import_file
    from qpcr_core.importers.base import add_report
    from qpcr_core.models import Project
    from tests.curve_factory import flat, logistic, melt

    project = Project()
    seed = 0
    for index, name in enumerate(("demo_run1.csv", "demo_run2.csv"), start=1):
        add_report(project, import_file(OUT / name, f"R{index}"))
    for run in project.runs:
        for well in run.wells.values():
            for r in well.reactions:
                seed += 1
                if r.cq is None:
                    r.amplification = flat(drift=0.001, noise=0.002, seed=seed)
                    r.melt = melt(height=0.0, noise=0.002, seed=seed)
                else:
                    r.amplification = logistic(r.cq, efficiency=0.95, drift=0.001, noise=0.002, seed=seed)
                    r.melt = melt(tm=84.5 if r.target == "GAPDH" else 81.0, noise=0.002, seed=seed)
    project.targets["GAPDH"].kind = "reference"
    project.settings.control_group = "Ctrl"
    return project


def main() -> None:
    rng = random.Random(42)
    for name, groups, shift, std in (("demo_run1.csv", ["Ctrl", "LPS"], 0.0, True), ("demo_run2.csv", ["LPS+Dex"], 0.5, False)):
        with open(OUT / name, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(HEADER)
            w.writerows(plate(groups, shift, rng, std))
    from qpcr_core.sessions import save_project

    path = OUT / "demo_project.qpcrkit.json"
    save_project(demo_project(), path)
    path.with_name(path.name + ".bak").unlink(missing_ok=True)


if __name__ == "__main__":
    main()

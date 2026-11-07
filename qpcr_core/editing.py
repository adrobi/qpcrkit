"""Annotation operations on a project and snapshot-based undo history (Qt-free)."""

from __future__ import annotations

import dataclasses

from .models import PLATE_FORMATS, Project, Reaction, Sample, Target, format_coord


def _reactions(project: Project, run_id: str, coords: list[str], target: str | None) -> list[Reaction]:
    wells = project.run(run_id).wells
    return [r for c in coords for r in wells[c].reactions if target is None or r.target == target]


def assign_sample(project: Project, run_id: str, coords: list[str], sample: str | None) -> None:
    sample = (sample or "").strip() or None
    for c in coords:
        project.run(run_id).wells[c].sample = sample
    if sample:
        project.samples.setdefault(sample, Sample(sample))
    project.prune_orphans()


def set_role(project: Project, run_id: str, coords: list[str], role: str, target: str | None = None) -> None:
    for r in _reactions(project, run_id, coords, target):
        r.role = role


def set_quantity(
    project: Project, run_id: str, coords: list[str], quantity: float | None, target: str | None = None
) -> None:
    for r in _reactions(project, run_id, coords, target):
        r.quantity = quantity


def set_group(project: Project, sample: str, group: str) -> None:
    project.samples.setdefault(sample, Sample(sample)).group = group.strip()


def set_excluded(project: Project, run_id: str, coord: str, target: str | None, excluded: bool, reason: str = "") -> None:
    for r in _reactions(project, run_id, [coord], target):
        r.excluded = excluded
        r.exclude_reason = reason if excluded else ""


def apply_sample_table(project: Project, rows: list[list[str]]) -> int:
    """Rows pasted from a spreadsheet: sample, group[, biological replicate]."""
    n = 0
    for row in rows:
        cells = [c.strip() for c in row]
        if not cells or not cells[0]:
            continue
        s = project.samples.setdefault(cells[0], Sample(cells[0]))
        if len(cells) > 1:
            s.group = cells[1]
        if len(cells) > 2:
            s.bio_replicate = cells[2]
        n += 1
    return n


def set_target_kind(project: Project, target: str, kind: str) -> None:
    project.targets.setdefault(target, Target(target)).kind = kind


def update_settings(project: Project, **changes) -> None:
    names = {f.name for f in dataclasses.fields(project.settings)}
    for key, value in changes.items():
        if key not in names:
            raise AttributeError(f"Unknown setting: {key}")
        setattr(project.settings, key, value)


def set_target(project: Project, run_id: str, coords: list[str], target: str, fluor: str | None = None) -> None:
    target = target.strip()
    if not target:
        return
    wells = project.run(run_id).wells
    for c in coords:
        for r in wells[c].reactions:
            if fluor is None or r.fluor == fluor:
                r.target = target
    project.targets.setdefault(target, Target(target))
    project.prune_orphans()


def rename_target_in_run(project: Project, run_id: str, old: str, new: str) -> None:
    """"All SYBR on this plate is GAPDH": settings go along, and a reference stays a reference."""
    new = new.strip()
    if not new or new == old:
        return
    run = project.run(run_id)
    for well in run.wells.values():
        for r in well.reactions:
            if r.target == old:
                r.target = new
    if old in run.thresholds:
        run.thresholds.setdefault(new, run.thresholds[old])
    source = project.targets.get(old)
    if new not in project.targets:
        project.targets[new] = dataclasses.replace(source, name=new) if source else Target(new)
    elif source:
        into = project.targets[new]
        if source.kind == "reference":
            into.kind = "reference"
        if into.efficiency_mode == "stdcurve" and into.efficiency_manual is None:  # nothing set on it yet
            into.efficiency_mode, into.efficiency_manual = source.efficiency_mode, source.efficiency_manual
        if into.stability_candidate is None:
            into.stability_candidate = source.stability_candidate
    project.prune_orphans()


def set_stability_candidate(project: Project, target: str, value: bool | None) -> None:
    """Whether a target takes part in the ranking of references; None goes back to the default."""
    project.targets.setdefault(target, Target(target)).stability_candidate = value


def set_references(project: Project, references: list[str], among: list[str]) -> None:
    """The given genes become references, the rest of ``among`` become targets; others are not touched."""
    for name in among:
        project.targets.setdefault(name, Target(name)).kind = "reference" if name in references else "target"


def set_threshold(project: Project, run_id: str, target: str, value: float | None) -> None:
    """A manual threshold for a target on a run; None goes back to the automatic one."""
    run = project.run(run_id)
    if value is None:
        run.thresholds.pop(target, None)
    elif value <= 0:
        raise ValueError("threshold must be positive")
    else:
        run.thresholds[target] = float(value)


def fill_series(
    project: Project, run_id: str, coords: list[str], prefix: str, start: int = 1, replicates: int = 1
) -> None:
    """Name wells in order: Ctrl-1 three times, Ctrl-2 three times, and so on."""
    wells = project.run(run_id).wells
    for i, c in enumerate(coords):
        name = f"{prefix}{start + i // max(replicates, 1)}"
        wells[c].sample = name
        project.samples.setdefault(name, Sample(name))
    project.prune_orphans()


def apply_plate_map(project: Project, run_id: str, rows: list[list[str]]) -> int:
    """A sample table shaped like the plate, as pasted from a spreadsheet; empty cells change nothing."""
    run = project.run(run_id)
    shape = PLATE_FORMATS.get(run.plate_format)
    if shape is None or not rows:
        return 0
    cells = [[c.strip() for c in row] for row in rows]
    if [c for c in cells[0][1:] if c][:2] == ["1", "2"]:  # column numbers and row letters copied too
        cells = [row[1:] for row in cells[1:]]
    changed = 0
    for r, row in enumerate(cells[: shape[0]]):
        for c, name in enumerate(row[: shape[1]]):
            well = run.wells.get(format_coord(r, c))
            if name and well is not None:
                well.sample = name
                project.samples.setdefault(name, Sample(name))
                changed += 1
    project.prune_orphans()
    return changed


def clone_project(p: Project) -> Project:
    """A copy for undo: containers are new, immutable curves are shared."""
    r = dataclasses.replace
    return Project(
        runs=[
            r(run, thresholds=dict(run.thresholds), wells={c: r(w, reactions=[r(x) for x in w.reactions]) for c, w in run.wells.items()})
            for run in p.runs
        ],
        targets={k: r(v) for k, v in p.targets.items()},
        samples={k: r(v) for k, v in p.samples.items()},
        settings=r(p.settings),
    )


class EditHistory:
    """Snapshots taken before each edit; undo and redo hand back a stored Project."""

    def __init__(self, max_depth: int = 100) -> None:
        self.max_depth = max_depth
        self._undo: list[Project] = []
        self._redo: list[Project] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def record(self, project: Project) -> None:
        self._undo.append(clone_project(project))
        del self._undo[: -self.max_depth]
        self._redo.clear()

    def undo(self, project: Project) -> Project | None:
        if not self._undo:
            return None
        self._redo.append(clone_project(project))
        return self._undo.pop()

    def redo(self, project: Project) -> Project | None:
        if not self._redo:
            return None
        self._undo.append(clone_project(project))
        return self._redo.pop()

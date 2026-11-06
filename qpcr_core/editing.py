"""Annotation operations on a project and snapshot-based undo history (Qt-free)."""

from __future__ import annotations

import dataclasses

from .models import Project, Reaction, Sample, Target


def _reactions(project: Project, run_id: str, coords: list[str], target: str | None) -> list[Reaction]:
    wells = project.run(run_id).wells
    return [r for c in coords for r in wells[c].reactions if target is None or r.target == target]


def assign_sample(project: Project, run_id: str, coords: list[str], sample: str | None) -> None:
    sample = (sample or "").strip() or None
    for c in coords:
        project.run(run_id).wells[c].sample = sample
    if sample:
        project.samples.setdefault(sample, Sample(sample))


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


def clone_project(p: Project) -> Project:
    """A copy for undo: containers are new, immutable curves are shared."""
    r = dataclasses.replace
    return Project(
        runs=[
            r(run, wells={c: r(w, reactions=[r(x) for x in w.reactions]) for c, w in run.wells.items()})
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

"""Compact project builder for calculation tests."""

from __future__ import annotations

from qpcr_core.models import Project, Reaction, Run, Sample, Settings, Target, Well

# run_id, coord, sample, target, role, cq, quantity
Row = tuple[str, str, "str | None", str, str, "float | None", "float | None"]


def make_project(
    rows: list[Row],
    groups: dict[str, str] | None = None,
    refs: tuple[str, ...] = (),
    control_group: str = "",
    **settings,
) -> Project:
    p = Project(settings=Settings(control_group=control_group, **settings))
    runs: dict[str, Run] = {}
    for run_id, coord, sample, target, role, cq, quantity in rows:
        run = runs.get(run_id)
        if run is None:
            run = runs[run_id] = Run(id=run_id, name=run_id)
            p.runs.append(run)
        well = run.wells.setdefault(coord, Well(coord, sample))
        well.reactions.append(Reaction(target=target, role=role, cq=cq, quantity=quantity))
    p.ensure_targets_and_samples()
    for name in refs:
        p.targets.setdefault(name, Target(name)).kind = "reference"
    for name, group in (groups or {}).items():
        p.samples.setdefault(name, Sample(name)).group = group
    return p

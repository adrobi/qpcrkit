"""What the user should do next: the line above the workspace."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Project


@dataclass(frozen=True)
class Hint:
    key: str
    params: dict = field(default_factory=dict)
    page: str = "plate"


def next_hint(project: Project) -> Hint | None:
    """The most important thing missing, or None when nothing is."""
    if not project.runs:
        return None
    unassigned = len(project.unassigned_targets())
    if unassigned:
        return Hint("hint.no_target", {"count": unassigned})

    nameless: set[tuple[str, str]] = set()
    named: set[str] = set()
    for run, well, rxn in project.iter_reactions():
        if rxn.role != "unknown" or rxn.excluded:
            continue
        if well.sample:
            named.add(well.sample)
        else:
            nameless.add((run.id, well.coord))
    if nameless:
        return Hint("hint.no_sample", {"count": len(nameless)})

    if not any(t.kind == "reference" for t in project.targets.values()):
        return Hint("hint.no_reference")

    ungrouped = [n for n in named if not (project.samples.get(n) and project.samples[n].group)]
    if ungrouped:
        return Hint("hint.no_groups", {"count": len(ungrouped)})

    s = project.settings
    if not s.control_group and not s.calibrator_sample:
        return Hint("hint.no_control")
    return None

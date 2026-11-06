"""Group files selected together into runs: CFX writes one file per table of a run."""

from __future__ import annotations

import re
from pathlib import Path

SUFFIX_RE = re.compile(
    r"(?: - +\s*(?:Quantification|Melt Curve|End Point|Run Information|ANOVA|Standard Curve|Gene Expression).*"
    r"|_Run Information)$"
)


def run_key(path: Path) -> str | None:
    """The run a CFX table belongs to, or None for a file that is not one of its tables."""
    stem = path.stem
    prefix = SUFFIX_RE.sub("", stem)
    return prefix if prefix != stem else None


def _expand(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            out.extend(sorted(x for x in p.rglob("*") if x.is_file()))
        else:
            out.append(p)
    return out


def group_files(paths: list[Path]) -> list[list[Path]]:
    """One group per run, in order of first appearance; other files stay alone."""
    groups: dict[tuple[Path, str] | Path, list[Path]] = {}
    for p in _expand([Path(x) for x in paths]):
        key = run_key(p)
        groups.setdefault((p.parent, key) if key is not None else p, []).append(p)
    return list(groups.values())

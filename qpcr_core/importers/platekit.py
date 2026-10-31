"""Plate layouts from platekit: its .platekit.json or the instrument layout CSVs it exports."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from ..models import Project, Sample
from .base import column_index, find_header, map_role, normalize_coord
from .textio import parse_number, read_rows

# platekit roles: unknown, ntc, pos, std, ipc (internal positive control), empty
_PLATEKIT_ROLES = {"unknown": "unknown", "ntc": "ntc", "pos": "pos", "std": "std", "ipc": "pos"}


@dataclass
class LayoutWell:
    coord: str
    sample: str = ""
    target: str = ""
    role: str = ""
    group: str = ""
    quantity: float | None = None


def read_platekit_json(path: str | os.PathLike) -> dict[str, LayoutWell]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, LayoutWell] = {}
    for w in data.get("plate", {}).get("wells", []):
        role = _PLATEKIT_ROLES.get(w.get("role", ""))
        if role is None:
            continue
        coord = normalize_coord(str(w["coord"]))
        out[coord] = LayoutWell(
            coord,
            sample=w.get("sample") or "",
            target=w.get("assay") or "",
            role=role,
            group=w.get("replicate_group") or "",
            quantity=w.get("std_quantity"),
        )
    return out


def read_instrument_layout(path: str | os.PathLike) -> dict[str, LayoutWell]:
    rows = read_rows(path)
    h = next(
        (i for i, r in enumerate(rows) if {"well", "well position", "no."} & {c.lower() for c in r}),
        None,
    )
    if h is None:
        raise ValueError(f"No layout table found in {path}")
    col = column_index(rows[h])

    def get(row: list[str], *names: str) -> str:
        for name in names:
            i = col.get(name)
            if i is not None and i < len(row) and row[i].strip():
                return row[i].strip()
        return ""

    out: dict[str, LayoutWell] = {}
    for row in rows[h + 1 :]:
        try:
            coord = normalize_coord(get(row, "well position", "well", "no."))
        except ValueError:
            continue
        role = map_role(get(row, "content", "task", "type") or "unknown")
        out[coord] = LayoutWell(
            coord,
            sample=get(row, "sample name", "sample", "name"),
            target=get(row, "target name", "target"),
            role=role,
            group=get(row, "biological set name", "biogroup name"),
            quantity=parse_number(get(row, "starting quantity", "quantity", "given conc")) if role == "std" else None,
        )
    return out


def apply_layout(project: Project, run_id: str, layout: dict[str, LayoutWell]) -> int:
    run = project.run(run_id)
    changed = 0
    for coord, lw in layout.items():
        well = run.wells.get(coord)
        if well is None:
            continue
        if lw.sample:
            well.sample = lw.sample
            s = project.samples.setdefault(lw.sample, Sample(lw.sample))
            if lw.group:
                s.group = lw.group
        for rxn in well.reactions:
            if lw.target and rxn.target != lw.target:
                continue
            if lw.role:
                rxn.role = lw.role
            if lw.role == "std":
                rxn.quantity = lw.quantity
        changed += 1
    return changed

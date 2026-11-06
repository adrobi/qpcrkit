"""Any table with a user-supplied column mapping (the CSV wizard)."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from ..models import Reaction, Run, coord_from_index
from .base import ImportReport, ReportBuilder, map_role, normalize_coord
from .textio import parse_cq


@dataclass
class ColumnMapping:
    well: str
    target: str
    cq: str
    sample: str | None = None
    role: str | None = None
    quantity: str | None = None
    group: str | None = None
    header_row: int = 0

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ColumnMapping:
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


def parse(
    rows: list[list[str]],
    mapping: ColumnMapping,
    source: str,
    run_id: str,
    plate_format: int = 96,
    delimiter: str | None = None,
) -> ImportReport:
    header = [c.strip() for c in rows[mapping.header_row]]
    idx: dict[str, int | None] = {}
    for field in ("well", "target", "cq", "sample", "role", "quantity", "group"):
        name = getattr(mapping, field)
        if name is None:
            idx[field] = None
        elif name in header:
            idx[field] = header.index(name)
        else:
            raise ValueError(f"Column not found: {name}")

    b = ReportBuilder(Run(id=run_id, name=source, source_file=source, instrument="generic", plate_format=plate_format))
    q = idx["quantity"]
    read_quantity = b.number_reader(
        [r[q] for r in rows[mapping.header_row + 1 :] if q is not None and q < len(r)], mapping.quantity or "", delimiter
    )
    for n, row in enumerate(rows[mapping.header_row + 1 :], start=mapping.header_row + 2):

        def get(field: str) -> str:
            i = idx[field]
            return row[i].strip() if i is not None and i < len(row) else ""

        b.row()
        pos = get("well")
        try:
            coord = coord_from_index(int(pos), plate_format) if pos.isdigit() else normalize_coord(pos)
        except ValueError:
            b.skip(n, "bad well coordinate")
            continue
        if not get("target"):
            b.skip(n, "no target")
            continue
        role = map_role(get("role")) if get("role") else "unknown"
        b.add(
            coord,
            get("sample"),
            Reaction(
                target=get("target"),
                role=role,
                cq=parse_cq(get("cq")),
                quantity=read_quantity(get("quantity")) if role == "std" else None,
            ),
            group=get("group"),
        )
    return b.report

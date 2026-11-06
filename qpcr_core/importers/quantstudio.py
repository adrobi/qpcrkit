"""Applied Biosystems QuantStudio / 7500 "Results" export (TXT/CSV/XLSX)."""

from __future__ import annotations

from ..models import Reaction, Run, coord_from_index
from .base import ImportReport, ReportBuilder, column_index, map_role, normalize_coord
from .textio import parse_cq

_CQ_HEADERS = ("ct", "cq", "cт")


def _header(rows: list[list[str]]) -> int | None:
    # A [Sample Setup] table may precede [Results]: take the first one that has a Cq column.
    for i, row in enumerate(rows):
        cells = {c.lower() for c in row}
        if {"sample name", "target name"} <= cells and cells & set(_CQ_HEADERS):
            return i
    return None


def sniff(rows: list[list[str]]) -> bool:
    return _header(rows) is not None


def _plate_format(rows: list[list[str]]) -> int:
    for row in rows:
        line = " ".join(row)
        if "block type" in line.lower():
            return 384 if "384" in line else 96
    return 96


def parse(rows: list[list[str]], source: str, run_id: str, delimiter: str | None = None) -> ImportReport:
    h = _header(rows)
    if h is None:
        raise ValueError("Not a QuantStudio results table")
    fmt = _plate_format(rows[:h])
    col = column_index(rows[h])
    cq_col = next(c for c in _CQ_HEADERS if c in col)

    def get(row: list[str], name: str) -> str:
        i = col.get(name)
        return row[i].strip() if i is not None and i < len(row) else ""

    b = ReportBuilder(Run(id=run_id, name=source, source_file=source, instrument="quantstudio", plate_format=fmt))
    read_quantity = b.number_reader([get(r, "quantity") for r in rows[h + 1 :]], "Quantity", delimiter)
    for n, row in enumerate(rows[h + 1 :], start=h + 2):
        if row and row[0].startswith("["):  # next section, e.g. [Amplification Data]
            break
        b.row()
        pos = get(row, "well position") or get(row, "well")
        try:
            coord = coord_from_index(int(pos), fmt) if pos.isdigit() else normalize_coord(pos)
        except ValueError:
            b.skip(n, "bad well coordinate")
            continue
        target = get(row, "target name")
        if not target:
            b.skip(n, "no target")
            continue
        role = map_role(get(row, "task"))
        omitted = get(row, "omit").lower() == "true"
        b.add(
            coord,
            get(row, "sample name"),
            Reaction(
                target=target,
                fluor=get(row, "reporter"),
                role=role,
                cq=parse_cq(get(row, cq_col)),
                quantity=read_quantity(get(row, "quantity")) if role == "std" else None,
                excluded=omitted,
                exclude_reason="omitted in instrument" if omitted else "",
            ),
            group=get(row, "biogroup name"),
        )
    return b.report

"""Bio-Rad CFX Maestro "Quantification Cq Results" export."""

from __future__ import annotations

from ..models import Reaction, Run
from .base import ImportReport, ReportBuilder, column_index, find_header, map_role, normalize_coord
from .textio import parse_cq

_REQUIRED = ("Well", "Fluor", "Content", "Cq")


def sniff(rows: list[list[str]]) -> bool:
    return find_header(rows, *_REQUIRED) is not None


def parse(rows: list[list[str]], source: str, run_id: str, delimiter: str | None = None) -> ImportReport:
    h = find_header(rows, *_REQUIRED)
    if h is None:
        raise ValueError("Not a CFX Cq results table")
    col = column_index(rows[h])

    def get(row: list[str], name: str) -> str:
        i = col.get(name.lower())
        return row[i].strip() if i is not None and i < len(row) else ""

    b = ReportBuilder(Run(id=run_id, name=source, source_file=source, instrument="cfx"))
    read_quantity = b.number_reader(
        [get(r, "Starting Quantity (SQ)") for r in rows[h + 1 :]], "Starting Quantity (SQ)", delimiter
    )
    for n, row in enumerate(rows[h + 1 :], start=h + 2):
        b.row()
        try:
            coord = normalize_coord(get(row, "Well"))
        except ValueError:
            b.skip(n, "bad well coordinate")
            continue
        target = get(row, "Target") or get(row, "Fluor")
        if not target:
            b.skip(n, "no target")
            continue
        content = get(row, "Content")
        role = map_role(content)
        quantity = read_quantity(get(row, "Starting Quantity (SQ)")) if role == "std" else None
        b.add(
            coord,
            get(row, "Sample"),
            Reaction(target=target, fluor=get(row, "Fluor"), role=role, cq=parse_cq(get(row, "Cq")), quantity=quantity),
            group=get(row, "Biological Set Name"),
        )
    return b.report

"""Bio-Rad CFX Maestro "Quantification Cq Results" export."""

from __future__ import annotations

from pathlib import Path

from ..models import Curve, Reaction, Run, Well
from .base import ImportReport, ReportBuilder, column_index, find_header, map_role, normalize_coord
from .textio import detect_number_style, parse_cq, parse_number, read_table

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


AMPLIFICATION = "Quantification Amplification Results"
MELT_RFU = "Melt Curve RFU Results"
MELT_DERIVATIVE = "Melt Curve Derivative Results"
CQ_TABLE = "Quantification Cq Results"


def _wide_table(path: Path) -> dict[str, Curve]:
    """A table with the cycle or temperature in the first named column and one column per well."""
    rows, delimiter = read_table(path)
    head = next(r for r in rows if any(r))
    axis = next(i for i, c in enumerate(head) if c)
    data = rows[rows.index(head) + 1 :]
    curves: dict[str, Curve] = {}
    for i in range(axis + 1, len(head)):
        if not head[i]:
            continue
        try:
            coord = normalize_coord(head[i])
        except ValueError:
            continue
        style = detect_number_style([r[i] for r in data if i < len(r)], delimiter)[0]
        xy = [(parse_number(r[axis]), parse_number(r[i], style)) for r in data if i < len(r)]
        xy = [(x, y) for x, y in xy if x is not None and y is not None]
        if xy:
            curves[coord] = Curve([x for x, _ in xy], [y for _, y in xy])
    return curves


def _dye(path: Path) -> str:
    return path.stem.rsplit("_", 1)[-1] if "_" in path.stem else ""


def attach_curves(report: ImportReport, curve_files: list[Path]) -> None:
    """Add amplification and melt tables to reactions by well and dye."""
    files = sorted(curve_files, key=lambda p: MELT_DERIVATIVE in p.name)  # raw melt curves first
    for path in files:
        dye = _dye(path)
        for coord, curve in _wide_table(path).items():
            well = report.run.wells.get(coord)
            if well is None:
                continue
            match = [r for r in well.reactions if r.fluor == dye] or (well.reactions if len(well.reactions) == 1 else [])
            for r in match:
                if AMPLIFICATION in path.name:
                    r.amplification, r.baseline_subtracted = curve, True
                elif MELT_RFU in path.name:
                    r.melt = curve
                elif MELT_DERIVATIVE in path.name and r.melt is None:
                    r.melt_derivative = curve


def report_from_curves(curve_files: list[Path], source: str, run_id: str) -> ImportReport:
    """A run from curve tables alone: reactions exist, Cq comes later from our own calculation."""
    b = ReportBuilder(Run(id=run_id, name=source, source_file=source, instrument="cfx"))
    for path in curve_files:
        dye = _dye(path)
        for coord in _wide_table(path):
            well = b.report.run.wells.setdefault(coord, Well(coord))
            if not any(r.fluor == dye for r in well.reactions):
                b.row()
                b.add(coord, "", Reaction(target=dye, fluor=dye))
    if len(b.report.run.wells) > 96:
        b.report.run.plate_format = 384
    attach_curves(b.report, curve_files)
    return b.report

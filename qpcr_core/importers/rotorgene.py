"""Qiagen Rotor-Gene Q "Quantitation" export: one table per channel."""

from __future__ import annotations

import re

from ..models import Reaction, Run
from .base import ImportReport, ReportBuilder, column_index, find_header, map_role
from .textio import parse_cq, parse_number

_SECTION_RE = re.compile(r"quantitation (?:data|information|results) for (.+)", re.IGNORECASE)


def sniff(rows: list[list[str]]) -> bool:
    return find_header(rows, "No.", "Name", "Type", "Ct") is not None


def parse(rows: list[list[str]], source: str, run_id: str) -> ImportReport:
    if not sniff(rows):
        raise ValueError("Not a Rotor-Gene quantitation table")
    b = ReportBuilder(Run(id=run_id, name=source, source_file=source, instrument="rotorgene", plate_format=72))
    target = "Target1"
    col: dict[str, int] | None = None
    conc_col: int | None = None

    for n, row in enumerate(rows, start=1):
        m = _SECTION_RE.search(" ".join(row))
        if m:
            target = m.group(1).strip().rsplit(".", 1)[-1].strip() or "Target1"
            col = None
            continue
        lowered = {c.lower() for c in row}
        if {"no.", "name", "type", "ct"} <= lowered:
            col = column_index(row)
            conc_col = next((i for c, i in col.items() if c.startswith("given conc")), None)
            continue
        if col is None:
            continue

        def get(name: str) -> str:
            i = col.get(name)
            return row[i].strip() if i is not None and i < len(row) else ""

        b.row()
        pos = get("no.")
        if not pos.isdigit():
            b.skip(n, "bad rotor position")
            continue
        role = map_role(get("type"))
        quantity = None
        if role == "std" and conc_col is not None and conc_col < len(row):
            quantity = parse_number(row[conc_col])
        b.add(
            str(int(pos)),
            get("name"),
            Reaction(target=target, fluor=target, role=role, cq=parse_cq(get("ct")), quantity=quantity),
        )
    return b.report

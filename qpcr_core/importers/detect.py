"""Format detection and the single import entry point."""

from __future__ import annotations

import os
from pathlib import Path

from . import cfx, generic_csv, quantstudio, rotorgene
from .base import ImportReport, UnknownFormatError
from .generic_csv import ColumnMapping
from .textio import read_sheets, read_table

_PARSERS = {"cfx": cfx, "quantstudio": quantstudio, "rotorgene": rotorgene}


def detect_format(rows: list[list[str]]) -> str | None:
    for name, module in _PARSERS.items():
        if module.sniff(rows):
            return name
    return None


def import_file(path: str | os.PathLike, run_id: str, mapping: ColumnMapping | None = None) -> ImportReport:
    path = Path(path)
    rows, delimiter = read_table(path)
    sheets = read_sheets(path) if delimiter is None else None
    if sheets:
        rows = sheets.get("Results") or next(iter(sheets.values()))
    if mapping is not None:
        return generic_csv.parse(rows, mapping, path.name, run_id, delimiter=delimiter)
    fmt = detect_format(rows)
    if fmt is None:
        raise UnknownFormatError(f"Unrecognized export format: {path}")
    if fmt == "quantstudio":
        return quantstudio.parse(rows, path.name, run_id, delimiter, sheets)
    return _PARSERS[fmt].parse(rows, path.name, run_id, delimiter)

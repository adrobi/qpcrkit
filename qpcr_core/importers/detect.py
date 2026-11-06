"""Format detection and the single import entry point."""

from __future__ import annotations

import os
from pathlib import Path

from . import cfx, generic_csv, quantstudio, rotorgene
from .grouping import group_files, run_key
from .base import ImportReport, UnknownFormatError
from .generic_csv import ColumnMapping
from .rdml import is_rdml, parse_rdml
from .textio import UnsupportedFileError, is_workbook, read_sheets, read_table

_PARSERS = {"cfx": cfx, "quantstudio": quantstudio, "rotorgene": rotorgene}


def detect_format(rows: list[list[str]]) -> str | None:
    for name, module in _PARSERS.items():
        if module.sniff(rows):
            return name
    return None


def import_file(path: str | os.PathLike, run_id: str, mapping: ColumnMapping | None = None) -> ImportReport:
    path = Path(path)
    if is_rdml(path):
        report = parse_rdml(path)[0]
        report.run.id = run_id
        return report
    sheets, delimiter = None, None
    if is_workbook(path):
        sheets = read_sheets(path)
        rows = sheets.get("Results") or next(iter(sheets.values()))
    else:
        rows, delimiter = read_table(path)
    if mapping is not None:
        return generic_csv.parse(rows, mapping, path.name, run_id, delimiter=delimiter)
    fmt = detect_format(rows)
    if fmt is None:
        raise UnknownFormatError(f"Unrecognized export format: {path}")
    if fmt == "quantstudio":
        return quantstudio.parse(rows, path.name, run_id, delimiter, sheets)
    return _PARSERS[fmt].parse(rows, path.name, run_id, delimiter)


def _import_cfx_group(files: list[Path], run_id: str) -> ImportReport | None:
    cq = [p for p in files if cfx.CQ_TABLE in p.name]
    curves = [p for p in files if any(t in p.name for t in (cfx.AMPLIFICATION, cfx.MELT_RFU, cfx.MELT_DERIVATIVE))]
    if cq:
        report = import_file(cq[0], run_id)
        cfx.attach_curves(report, curves)
        return report
    if curves:
        return cfx.report_from_curves(curves, run_key(files[0]) or files[0].stem, run_id)
    return None


def import_files(
    paths: list[str | os.PathLike], first_run_index: int = 1, mapping: ColumnMapping | None = None
) -> list[ImportReport]:
    """Everything selected together: folders, RDML with several runs, CFX tables of one run."""
    groups = group_files([Path(p) for p in paths])
    single = sum(len(g) for g in groups) == 1
    reports: list[ImportReport] = []
    ignored: list[str] = []
    binary = False
    for group in groups:
        run_id = f"R{first_run_index + len(reports)}"
        path = group[0]
        try:
            if len(group) == 1 and is_rdml(path):
                reports.extend(parse_rdml(path, first_run_index + len(reports)))
            elif run_key(path) is not None:
                report = _import_cfx_group(group, run_id)
                if report is not None:
                    reports.append(report)
            else:
                reports.append(import_file(path, run_id, mapping))
        except UnsupportedFileError:
            binary = True
            ignored.append(path.name)
        except UnknownFormatError:
            if single:
                raise
            ignored.append(path.name)
    if not reports:
        if binary:
            raise UnsupportedFileError(", ".join(ignored))
        raise UnknownFormatError(", ".join(str(p) for p in paths))
    if ignored:
        reports[0].notes.append("Not imported: " + ", ".join(ignored))
    return reports

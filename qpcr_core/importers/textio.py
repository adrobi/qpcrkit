"""Read instrument exports (CSV/TXT/XLSX) into rows of stripped strings."""

from __future__ import annotations

import csv
import io
import os
from collections import Counter
from pathlib import Path

_DELIMITERS = ("\t", ";", ",")
_MISSING_CQ = {"undetermined", "n/a", "na", "nan", "no ct", "no cq", "—", "-", ""}


def _decode(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1251")


def _pick_delimiter(lines: list[str]) -> str:
    sample = [ln for ln in lines[:50] if ln.strip()]
    best, best_score = ",", -1
    for d in _DELIMITERS:
        counts = Counter(len(next(csv.reader([ln], delimiter=d))) for ln in sample)
        score = max((n for cols, n in counts.items() if cols >= 2), default=0)
        if score > best_score:
            best, best_score = d, score
    return best


def _cell(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return repr(v)
    return str(v).strip()


def _read_xlsx(path: Path) -> list[list[str]]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb["Results"] if "Results" in wb.sheetnames else wb.worksheets[0]
        rows = [[_cell(v) for v in row] for row in ws.iter_rows(values_only=True)]
    finally:
        wb.close()
    return [r for r in rows if any(r)]


def read_rows(path: str | os.PathLike) -> list[list[str]]:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        return _read_xlsx(path)
    text = _decode(path.read_bytes())
    lines = text.splitlines()
    reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=_pick_delimiter(lines))
    return [[c.strip() for c in row] for row in reader if any(c.strip() for c in row)]


def parse_number(s: str) -> float | None:
    s = s.strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_cq(s: str) -> float | None:
    if s.strip().lower() in _MISSING_CQ:
        return None
    value = parse_number(s)
    if value is None or value != value:  # NaN
        return None
    return value

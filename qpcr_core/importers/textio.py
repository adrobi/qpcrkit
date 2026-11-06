"""Read instrument exports (CSV/TXT/XLSX) into rows of stripped strings; parse their numbers."""

from __future__ import annotations

import csv
import io
import os
import re
from collections import Counter
from pathlib import Path

_DELIMITERS = ("\t", ";", ",")
_MISSING_CQ = {"undetermined", "n/a", "na", "nan", "no ct", "no cq", "—", "-", ""}
_BINARY_SUFFIXES = {".pcrd", ".eds", ".xls", ".rex", ".zip"}
_THOUSANDS_LOOK = re.compile(r"^[+-]?[1-9]\d{0,2},\d{3}$")
_THOUSANDS_NUMBER = re.compile(r"^[+-]?[1-9]\d{0,2}(,\d{3})+([eE][+-]?\d+)?$")
_PLAIN_DECIMAL = re.compile(r"^[+-]?\d+\.\d+([eE][+-]?\d+)?$")
_NUMBER_LOOK = re.compile(r"^[+-]?[\d.,\s ]+([eE][+-]?\d+)?$")


class UnsupportedFileError(Exception):
    """A binary file we cannot read, such as the instrument's own project file."""


def _decode(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1251", errors="replace")


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


def _sheet_rows(ws) -> list[list[str]]:
    rows = [[_cell(v) for v in row] for row in ws.iter_rows(values_only=True)]
    return [r for r in rows if any(r)]


def is_workbook(path: str | os.PathLike) -> bool:
    return Path(path).suffix.lower() in (".xlsx", ".xlsm")


def _open_workbook(path: Path):
    import warnings

    import openpyxl

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # instruments write workbooks without a default style
        return openpyxl.load_workbook(path, read_only=True, data_only=True)


def read_sheets(path: str | os.PathLike) -> dict[str, list[list[str]]]:
    """All sheets of a workbook by name; a text file is one sheet named ""."""
    path = Path(path)
    if not is_workbook(path):
        return {"": read_table(path)[0]}
    wb = _open_workbook(path)
    try:
        return {ws.title: _sheet_rows(ws) for ws in wb.worksheets}
    finally:
        wb.close()


def _read_xlsx(path: Path) -> list[list[str]]:
    wb = _open_workbook(path)
    try:
        return _sheet_rows(wb["Results"] if "Results" in wb.sheetnames else wb.worksheets[0])
    finally:
        wb.close()


def read_table(path: str | os.PathLike) -> tuple[list[list[str]], str | None]:
    """Rows and the delimiter (None for a workbook)."""
    path = Path(path)
    if is_workbook(path):
        return _read_xlsx(path), None
    raw = path.read_bytes()
    if path.suffix.lower() in _BINARY_SUFFIXES or (
        not raw.startswith((b"\xff\xfe", b"\xfe\xff")) and b"\x00" in raw[:8192]
    ):
        raise UnsupportedFileError(f"Not a text table: {path}")
    lines = _decode(raw).splitlines()
    delimiter = _pick_delimiter(lines)
    reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter)
    return [[c.strip() for c in row] for row in reader if any(c.strip() for c in row)], delimiter


def read_rows(path: str | os.PathLike) -> list[list[str]]:
    return read_table(path)[0]


def detect_number_style(cells: list[str], delimiter: str | None = None) -> tuple[str, bool]:
    """What a comma means in a whole column: ("decimal_comma" | "thousands_comma", ambiguous).

    Deciding per cell would break a Russian dilution series: 10,000 / 5,000 / 1,250 / 0,625.
    """
    with_comma = [c.strip() for c in cells if "," in c and _NUMBER_LOOK.match(c.strip())]
    if not with_comma:
        return "decimal_comma", False
    for c in with_comma:
        if "." in c:
            return ("thousands_comma" if c.rfind(".") > c.rfind(",") else "decimal_comma"), False
        if c.count(",") > 1:
            return "thousands_comma", False
    if not all(_THOUSANDS_LOOK.match(c) for c in with_comma):
        return "decimal_comma", False
    if any(_PLAIN_DECIMAL.match(c.strip()) for c in cells):  # the same column uses a dot for decimals
        return "thousands_comma", False
    if delimiter == ";":
        return "decimal_comma", False
    return "thousands_comma", True


def parse_number(s: str, style: str = "decimal_comma") -> float | None:
    s = s.strip().replace(" ", "").replace(" ", "")
    if "," in s and "." in s:  # both present: the last one is the decimal separator
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif style == "thousands_comma" and _THOUSANDS_NUMBER.match(s):
        s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
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

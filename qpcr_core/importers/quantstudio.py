"""Applied Biosystems QuantStudio / 7500 exports: text sections and Design & Analysis workbooks."""

from __future__ import annotations

from collections import defaultdict

from ..models import Curve, Reaction, Run, coord_from_index
from .base import ImportReport, ReportBuilder, column_index, map_role, normalize_coord
from .textio import detect_number_style, parse_cq, parse_number

_CQ_HEADERS = ("ct", "cq", "cт", "crt")
_NAMES = ({"sample name", "target name"}, {"sample", "target"})
_NOT_NAMED = {"", "n/a", "na", "none", "-"}
_MELT_SHEETS = ("Melt Curve Raw", "Melt Curve Raw Data")


def _header(rows: list[list[str]]) -> int | None:
    # A [Sample Setup] table may precede [Results]: take the first one that has a Cq column.
    for i, row in enumerate(rows):
        cells = {c.lower() for c in row}
        if "task" in cells and any(n <= cells for n in _NAMES) and cells & set(_CQ_HEADERS):
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


def _meta_pair(row: list[str]) -> tuple[str, str] | None:
    """A metadata line, as "Key = Value" in one cell or Key and Value in two."""
    cells = [c for c in row if c]
    if len(cells) == 1 and "=" in cells[0]:
        key, value = cells[0].split("=", 1)
        return key.strip(" *").lower(), value.strip()
    if len(cells) == 2:
        return cells[0].strip(" *").lower(), cells[1]
    return None


def _apply_meta(report: ImportReport, rows: list[list[str]]) -> None:
    for row in rows:
        pair = _meta_pair(row)
        if pair is None or pair[1].lower() in _NOT_NAMED:
            continue
        if pair[0] == "endogenous control" and not report.suggested_refs:
            report.suggested_refs = [v.strip() for v in pair[1].replace(";", ",").split(",") if v.strip()]
        elif pair[0] == "reference sample" and not report.suggested_calibrator:
            report.suggested_calibrator = pair[1]


def _coord(pos: str, fmt: int) -> str:
    return coord_from_index(int(float(pos)), fmt) if pos.replace(".0", "", 1).isdigit() else normalize_coord(pos)


def _section(rows: list[list[str]], name: str) -> list[list[str]]:
    """Rows of a [Name] section of a text export."""
    start = next((i for i, r in enumerate(rows) if r and r[0].strip() == f"[{name}]"), None)
    if start is None:
        return []
    out: list[list[str]] = []
    for row in rows[start + 1 :]:
        if row and row[0].startswith("["):
            break
        out.append(row)
    return out


def _table(rows: list[list[str]], *required: str) -> tuple[list[list[str]], dict[str, int]] | None:
    """The data rows and columns of the first table having all ``required`` columns."""
    for i, row in enumerate(rows):
        col = column_index(row)
        if all(any(alt in col for alt in name.split("|")) for name in required):
            return rows[i + 1 :], col
    return None


def _pick(col: dict[str, int], names: str) -> int | None:
    return next((col[n] for n in names.split("|") if n in col), None)


def _cell(row: list[str], i: int | None) -> str:
    return row[i].strip() if i is not None and i < len(row) else ""


def _quantities(sheets: dict[str, list[list[str]]] | None, fmt: int) -> tuple[dict, dict]:
    """Design & Analysis keeps quantities on other sheets: by (coord, target) and (sample, target)."""
    by_well: dict[tuple[str, str], str] = {}
    by_group: dict[tuple[str, str], str] = {}
    if not sheets:
        return by_well, by_group
    found = _table(sheets.get("Standard Curve Result", []), "well position|well", "target name|target", "quantity", "task")
    if found:
        data, col = found
        well, target = _pick(col, "well position|well"), _pick(col, "target name|target")
        for r in data:
            if _cell(r, col["task"]).upper() != "STANDARD":
                continue
            try:
                by_well[(_coord(_cell(r, well), fmt), _cell(r, target))] = _cell(r, col["quantity"])
            except ValueError:
                continue
    found = _table(sheets.get("Replicate Group Result", []), "sample name|sample", "target name|target", "quantity")
    if found:
        data, col = found
        sample, target = _pick(col, "sample name|sample"), _pick(col, "target name|target")
        seen: dict[tuple[str, str], dict[float, str]] = defaultdict(dict)
        for r in data:
            value = _cell(r, col["quantity"])
            number = parse_number(value)
            if number is not None:
                seen[(_cell(r, sample), _cell(r, target))][number] = value
        by_group = {k: next(iter(v.values())) for k, v in seen.items() if len(v) == 1}  # ambiguous pairs stay empty
    return by_well, by_group


def _attach_curves(
    b: ReportBuilder,
    table: tuple[list[list[str]], dict[str, int]] | None,
    x_names: str,
    y_names: str,
    field: str,
    fmt: int,
    delimiter: str | None = None,
) -> None:
    """Long tables: one row per well, target and cycle or temperature."""
    if not table:
        return
    data, col = table
    well, target = _pick(col, "well position|well"), _pick(col, "target name|target")
    xc, yc = _pick(col, x_names), _pick(col, y_names)
    style, ambiguous = detect_number_style([_cell(r, yc) for r in data[:2000]], delimiter)
    if ambiguous:
        b.note(f"{field}: comma read as thousands in the curve values")
    points: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    for r in data:
        try:
            coord = _coord(_cell(r, well), fmt)
        except ValueError:
            continue
        x, y = parse_number(_cell(r, xc)), parse_number(_cell(r, yc), style)
        if x is not None and y is not None:
            points[(coord, _cell(r, target))].append((x, y))
    for (coord, name), xy in points.items():
        w = b.report.run.wells.get(coord)
        if w is None:
            continue
        if name:
            rxns = [x for x in w.reactions if x.target == name]
        elif len(w.reactions) == 1:
            rxns = w.reactions
        else:
            b.note(f"{field}: well {coord} has several targets and the table does not say which curve is whose")
            continue
        xy.sort()
        curve = Curve([p[0] for p in xy], [p[1] for p in xy])
        for x in rxns:
            setattr(x, field, curve)


def parse(
    rows: list[list[str]],
    source: str,
    run_id: str,
    delimiter: str | None = None,
    sheets: dict[str, list[list[str]]] | None = None,
) -> ImportReport:
    h = _header(rows)
    if h is None:
        raise ValueError("Not a QuantStudio results table")
    fmt = _plate_format(rows[:h])
    col = column_index(rows[h])
    cq_col = next(c for c in _CQ_HEADERS if c in col)

    def get(row: list[str], name: str) -> str:
        return _cell(row, _pick(col, name))

    b = ReportBuilder(Run(id=run_id, name=source, source_file=source, instrument="quantstudio", plate_format=fmt))
    by_well, by_group = _quantities(sheets, fmt)
    table = rows[h + 1 :]
    table = table[: next((i for i, r in enumerate(table) if r and r[0].startswith("[")), len(table))]
    q_cells = [get(r, "quantity") for r in table] + list(by_well.values()) + list(by_group.values())
    read_quantity = b.number_reader(q_cells, "Quantity", delimiter)
    _apply_meta(b.report, rows[:h])

    for n, row in enumerate(table, start=h + 2):
        pos = get(row, "well position|well")
        try:
            coord = _coord(pos, fmt)
        except ValueError:
            if not get(row, cq_col) and sum(bool(c) for c in row) <= 3:  # a footer line, not a data row
                _apply_meta(b.report, [row])
            else:
                b.row()
                b.skip(n, "bad well coordinate")
            continue
        b.row()
        target = get(row, "target name|target")
        if not target:
            b.skip(n, "no target")
            continue
        role = map_role(get(row, "task"))
        omitted = get(row, "omit").lower() == "true"
        sample = get(row, "sample name|sample")
        quantity = None
        if role == "std":
            quantity = read_quantity(get(row, "quantity"))  # may be a placeholder such as N/A
            if quantity is None:
                quantity = read_quantity(by_well.get((coord, target)) or by_group.get((sample, target), ""))
        b.add(
            coord,
            sample,
            Reaction(
                target=target,
                fluor=get(row, "reporter"),
                role=role,
                cq=parse_cq(get(row, cq_col)),
                quantity=quantity,
                excluded=omitted,
                exclude_reason="omitted in instrument" if omitted else "",
            ),
            group=get(row, "biogroup name|biogroup"),
        )

    if sheets:
        amp_rows = sheets.get("Amplification Data", [])
        melt_rows = next((sheets[s] for s in _MELT_SHEETS if s in sheets), [])
    else:
        amp_rows = _section(rows, "Amplification Data")
        melt_rows = _section(rows, "Melt Curve Raw Data")
    cycle = "cycle|cycle number"
    _attach_curves(b, _table(amp_rows, cycle, "rn"), cycle, "rn", "amplification", fmt, delimiter)
    _attach_curves(b, _table(melt_rows, "temperature", "fluorescence"), "temperature", "fluorescence", "melt", fmt, delimiter)
    return b.report

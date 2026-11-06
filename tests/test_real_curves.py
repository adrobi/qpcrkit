"""Curve analysis against what the instruments report; see tests/data/real/ATTRIBUTION.md."""

from pathlib import Path

import pytest

from qpcr_core import curves as cv
from qpcr_core.importers.textio import parse_number, read_sheets
from qpcr_core.models import Curve

REAL = Path(__file__).parent / "data" / "real"
QS1 = REAL / "appbio_quantstudio_designandanalysis_QS1_Standard_Curve_example01.xlsx"


def _table(rows: list[list[str]], *columns: str) -> tuple[list[list[str]], dict[str, int]]:
    for i, row in enumerate(rows):
        if all(c in row for c in columns):
            return rows[i + 1 :], {name: j for j, name in enumerate(row)}
    raise AssertionError(f"no table with {columns}")


def test_cq_at_matches_instrument_on_its_own_curves():
    sheets = read_sheets(QS1)
    data, col = _table(sheets["Results"], "Well Position", "Cq", "Threshold")
    expected = {}
    for r in data:
        cq, t = parse_number(r[col["Cq"]]), parse_number(r[col["Threshold"]])
        if cq is not None and t is not None:
            expected[(r[col["Well Position"]], r[col["Target"]])] = (cq, t)
    data, col = _table(sheets["Amplification Data"], "Well Position", "Cycle Number", "dRn")
    points: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for r in data:
        points.setdefault((r[col["Well Position"]], r[col["Target"]]), []).append(
            (parse_number(r[col["Cycle Number"]]), parse_number(r[col["dRn"]]))
        )
    assert len(expected) > 80
    for key, (cq, t) in expected.items():
        xy = sorted(points[key])
        got = cv.cq_at(Curve([p[0] for p in xy], [p[1] for p in xy]), t)
        assert got == pytest.approx(cq, abs=0.1), key

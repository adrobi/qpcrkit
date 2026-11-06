"""Curve analysis against what the instruments report; see tests/data/real/ATTRIBUTION.md."""

from pathlib import Path

import numpy as np
import pytest

from qpcr_core import curves as cv
from qpcr_core.importers.detect import import_file, import_files
from qpcr_core.importers.textio import parse_number, read_sheets
from qpcr_core.models import Curve, Project
from qpcr_core.pipeline import analyze

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


def test_tm_matches_instrument():
    path = REAL / "appbio_quantstudio_designandanalysis_QS7Pro_PCR_with_Melt_example09.xlsx"
    data, col = _table(read_sheets(path)["Results"], "Well Position", "Tm1")
    expected = {r[col["Well Position"]]: parse_number(r[col["Tm1"]]) for r in data if parse_number(r[col["Tm1"]]) is not None}
    assert len(expected) > 20
    run = import_file(path, "R1").run
    for coord, tm in expected.items():
        d = cv.melt_derivative(cv.clean(run.wells[coord].reactions[0].melt))
        peaks = cv.melt_peaks(d, cv.MELT_NOISE_FACTOR * cv.melt_noise(d))
        assert peaks, coord
        assert peaks[0] == pytest.approx(tm, abs=0.5), coord


# --- our results against the instruments, targets from the 1.1 spec ---

DA = "appbio_quantstudio_designandanalysis_"
QS3 = REAL / f"{DA}QS3_Relative_Quantification_example02.xlsx"
QS7 = REAL / f"{DA}QS7Pro_PCR_with_Melt_example09.xlsx"
STEPONE = REAL / "stepone_std.rdml"


def _analyzed(*paths):
    reports = import_files(list(paths), 1)
    assert len(reports) == 1
    project = Project(runs=[reports[0].run])
    project.ensure_targets_and_samples()
    return reports[0].run, analyze(project)


def _pairs(run, res, target):
    """(our Cq, instrument Cq, last cycle) of the reactions with a curve."""
    out = []
    for coord, well in run.wells.items():
        for r in well.reactions:
            if r.target == target and not r.excluded and r.amplification is not None:
                out.append((res.curves[(run.id, coord, r.target, r.fluor)].cq_calc, r.cq, r.amplification.x[-1]))
    return out


def _wendy_files():
    return sorted(REAL.glob("2016-09-04*"))


CASES = [
    pytest.param([QS1], "RNaseP", id="QS1"),
    pytest.param([QS3], "RNaseP", id="QS3-RNaseP"),
    pytest.param([QS3], "IPC", id="QS3-IPC"),
    pytest.param([QS7], "RNase P", id="QS7"),
    pytest.param([STEPONE], "RNase P", id="StepOne"),
    pytest.param(_wendy_files(), "SYBR", id="CFX"),
]


@pytest.mark.parametrize("paths,target", CASES)
def test_our_cq_differs_from_the_instrument_by_a_constant(paths, target):
    run, res = _analyzed(*paths)
    diffs = [ours - theirs for ours, theirs, _ in _pairs(run, res, target) if ours is not None and theirs is not None]
    assert len(diffs) >= 15
    assert np.std(diffs, ddof=1) <= 0.15


@pytest.mark.parametrize("paths,target", CASES)
def test_we_agree_on_which_reactions_amplified(paths, target):
    """A Cq equal to the last cycle is how StepOne writes that nothing came up."""
    run, res = _analyzed(*paths)
    pairs = _pairs(run, res, target)
    same = sum((ours is None) == (theirs is None or theirs >= last) for ours, theirs, last in pairs)
    assert same / len(pairs) >= 0.95


@pytest.mark.parametrize(
    "path,target",
    [
        pytest.param(QS3, "RNaseP", id="QS3"),
        pytest.param(STEPONE, "RNase P", id="StepOne"),
        pytest.param(
            QS1,
            "RNaseP",
            id="QS1",
            marks=pytest.mark.xfail(
                strict=True,
                reason="0.80 from the curves against 0.99 from the dilutions: on this noisy TaqMan plate the signal "
                "falls off the exponent right above the noise; shown to the user, the tolerance stays",
            ),
        ),
    ],
)
def test_efficiency_from_curves_is_close_to_the_standard_curve(path, target):
    _, res = _analyzed(path)
    standard = next(c.efficiency for (_, t), c in res.std_curves.items() if t == target)
    assert abs(res.curve_efficiency[target] - standard) <= 0.10


def test_tm_in_the_pipeline_matches_the_instrument():
    data, col = _table(read_sheets(QS7)["Results"], "Well Position", "Tm1")
    expected = {r[col["Well Position"]]: parse_number(r[col["Tm1"]]) for r in data if parse_number(r[col["Tm1"]]) is not None}
    run, res = _analyzed(QS7)
    checked = 0
    for coord, tm in expected.items():
        r = run.wells[coord].reactions[0]
        got = res.curves[(run.id, coord, r.target, r.fluor)].tms
        assert got and got[0] == pytest.approx(tm, abs=0.5), coord
        checked += 1
    assert checked >= 20


def test_subtracted_cfx_curves_do_not_overstate_efficiency_much():
    """No standards on this plate; the plateau of plausible PCR is the check, and the flag warns about the rest."""
    _, res = _analyzed(*_wendy_files())
    assert 0.85 <= res.curve_efficiency["SYBR"] <= 1.05

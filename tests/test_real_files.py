"""Importers on real instrument exports; see tests/data/real/ATTRIBUTION.md."""

from pathlib import Path

import pytest

from qpcr_core.importers.detect import detect_format, import_file
from qpcr_core.importers.textio import read_rows

REAL = Path(__file__).parent / "data" / "real"
DA = "appbio_quantstudio_designandanalysis_"
QS1 = REAL / f"{DA}QS1_Standard_Curve_example01.xlsx"
QS3 = REAL / f"{DA}QS3_Relative_Quantification_example02.xlsx"


def _reactions(rep):
    return [r for w in rep.run.wells.values() for r in w.reactions]


def test_design_and_analysis_standard_curve():
    assert detect_format(read_rows(QS1)) == "quantstudio"
    rep = import_file(QS1, "R1")
    rx = _reactions(rep)
    assert len(rep.run.wells) == 96 and rep.run.instrument == "quantstudio"
    assert sum(r.cq is None for r in rx) == 4
    assert {"std", "ntc", "unknown"} <= {r.role for r in rx}
    stds = [r for r in rx if r.role == "std"]
    assert stds and all(r.quantity and r.quantity > 0 for r in stds)
    assert rep.skipped == []


def test_design_and_analysis_curves():
    rep = import_file(QS1, "R1")
    r = rep.run.wells["A1"].reactions[0]
    assert r.amplification is not None and r.amplification.x[0] == 1.0
    assert len(r.amplification.x) == len(r.amplification.y) > 20
    assert r.baseline_subtracted is False


def test_design_and_analysis_relative_quantification():
    rep = import_file(QS3, "R1")
    rx = _reactions(rep)
    assert len(rx) == 156
    assert sum(r.cq is None for r in rx) == 4
    assert all(r.quantity and r.quantity > 0 for r in rx if r.role == "std")


def test_thousands_in_quantity_column():
    rep = import_file(REAL / "appbio_quantstudio_example04.txt", "R1")
    stds = [r for r in _reactions(rep) if r.role == "std"]
    assert len(stds) == 20 and all(r.quantity for r in stds)
    assert rep.run.wells["D5"].reactions[0].quantity == 1250.0
    assert rep.notes == []


def test_results_only_hundred_million():
    rep = import_file(REAL / "example_quantsudio_results_only.txt", "R1")
    assert rep.run.wells["A1"].reactions[0].quantity == 1e8
    assert rep.skipped == []


def test_footer_gives_suggestions_not_skips():
    rep = import_file(REAL / "appbio_quantstudio_example10.xlsx", "R1")
    assert rep.skipped == []
    assert rep.suggested_refs == ["RefGene"]
    assert rep.suggested_calibrator == "Sample_1"
    rep = import_file(REAL / "appbio_quantstudio_minimal_undetermined_standard.txt", "R1")
    assert rep.skipped == []
    assert rep.suggested_refs and rep.suggested_calibrator


def test_text_export_amplification_section():
    rep = import_file(REAL / "appbio_quantstudio_example01.txt", "R1")
    r = rep.run.wells["A1"].reactions[0]
    assert r.amplification is not None and r.amplification.y[0] == pytest.approx(0.612)


def test_cfx_maestro_real_export():
    rep = import_file(REAL / "cfx_maestro_example01.csv", "R1")
    assert rep.run.instrument == "cfx" and rep.imported == 48 and rep.skipped == []
    assert {r.target for r in _reactions(rep)} == {"FAM", "VIC"}


def _sheet_table(path, sheet, first_col):
    """Rows of a sheet as dicts, starting from the row whose first cell is ``first_col``."""
    from qpcr_core.importers.textio import read_sheets

    rows = read_sheets(path)[sheet]
    h = next(i for i, r in enumerate(rows) if r[0] == first_col)
    return [dict(zip(rows[h], r)) for r in rows[h + 1 :]]


def test_standard_curve_matches_instrument():
    """QS1: the instrument's own slope, intercept, R2 and efficiency for the same data."""
    from qpcr_core.importers.base import add_report
    from qpcr_core.models import Project
    from qpcr_core.pipeline import analyze

    table = _sheet_table(QS1, "Standard Curve Result", "Well")
    first = table[0]
    p = Project()
    add_report(p, import_file(QS1, "R1"))
    c = analyze(p).std_curves[(None, "RNaseP")]
    assert c.slope == pytest.approx(float(first["Slope"]), abs=0.005)
    assert c.intercept == pytest.approx(float(first["Y-Intercept"]), abs=0.02)
    assert c.r2 == pytest.approx(float(first["R2"]), abs=0.0005)
    assert c.efficiency * 100 == pytest.approx(float(first["Efficiency"]), abs=0.3)


def test_quantities_match_instrument():
    """QS1: quantity of each unknown well, from our curve, against the instrument's."""
    from qpcr_core.importers.base import add_report
    from qpcr_core.models import Project
    from qpcr_core.pipeline import analyze
    from qpcr_core.stdcurve import quantify

    p = Project()
    add_report(p, import_file(QS1, "R1"))
    curve = analyze(p).std_curves[(None, "RNaseP")]
    compared = 0
    for row in _sheet_table(QS1, "Standard Curve Result", "Well"):
        if row["Task"] == "UNKNOWN" and row["Cq"] not in ("", "UNDETERMINED"):
            q, _ = quantify(curve, float(row["Cq"]))
            assert q == pytest.approx(float(row["Quantity"]), rel=0.02)
            compared += 1
    assert compared > 10


def test_relative_quantity_matches_instrument():
    """QS3: RQ against the instrument's sheet, IPC as reference, Unk_400 as calibrator.

    The instrument corrects for efficiency ("EqCq"), with the efficiencies of its standard curves.
    """
    from qpcr_core.importers.base import add_report
    from qpcr_core.models import Project
    from qpcr_core.pipeline import analyze

    p = Project()
    add_report(p, import_file(QS3, "R1"))
    p.targets["IPC"].kind = "reference"
    p.settings.calibrator_sample = "Unk_400"
    for s in p.samples.values():
        s.group = "all"
    res = analyze(p)
    ours = {(r.sample, r.target): r.rq for r in res.rqs}
    compared = 0
    for row in _sheet_table(QS3, "RQ Replicate Group Result", "Sample"):
        if row["Rq"]:
            assert ours[(row["Sample"], row["Target"])] == pytest.approx(float(row["Rq"]), rel=0.001)
            compared += 1
    assert compared >= 3

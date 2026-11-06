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

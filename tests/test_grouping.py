from pathlib import Path

import pytest

from qpcr_core.importers.base import UnknownFormatError
from qpcr_core.importers.detect import import_files
from qpcr_core.importers.grouping import group_files
from qpcr_core.importers.textio import UnsupportedFileError

REAL = Path(__file__).parent / "data" / "real"
WENDY = sorted(REAL.glob("2016-09-04 gapdh*"))


def _names(groups):
    return [[p.name for p in g] for g in groups]


def test_plates_with_common_prefix_stay_apart(tmp_path):
    a = tmp_path / "Exp1 - Plate1 -  Quantification Cq Results.csv"
    b = tmp_path / "Exp1 - Plate2 -  Quantification Cq Results.csv"
    c = tmp_path / "Exp1 - Plate1 -  Quantification Amplification Results_SYBR.csv"
    for p in (a, b, c):
        p.write_text("x", encoding="utf-8")
    groups = group_files([a, b, c])
    assert len(groups) == 2
    assert {p.name for p in groups[0]} == {a.name, c.name}


def test_run_information_joins_the_group(tmp_path):
    a = tmp_path / "run1 -  Quantification Cq Results.csv"
    b = tmp_path / "run1_Run Information.csv"
    for p in (a, b):
        p.write_text("x", encoding="utf-8")
    assert len(group_files([a, b])) == 1


def test_folder_is_expanded(tmp_path):
    (tmp_path / "x.csv").write_text("a", encoding="utf-8")
    assert _names(group_files([tmp_path])) == [["x.csv"]]


def test_cfx_cq_with_curves():
    assert len(WENDY) == 4 and len(group_files(WENDY)) == 1
    reports = import_files(WENDY)
    assert len(reports) == 1
    rep = reports[0]
    r = rep.run.wells["A1"].reactions[0]
    assert len(rep.run.wells) == 96 and r.cq is not None
    assert len(r.amplification.x) == 40 and r.amplification.y[0] == pytest.approx(-41.1339, abs=1e-3)
    assert r.baseline_subtracted is True
    assert len(r.melt.x) == 61 and r.melt.x[0] == 65.0
    assert r.melt_derivative is None


def test_derivative_used_only_without_raw_melt():
    only = [p for p in WENDY if "RFU" not in p.name]
    r = import_files(only)[0].run.wells["A1"].reactions[0]
    assert r.melt is None and len(r.melt_derivative.x) == 61


def test_curves_without_cq_file():
    amp = [p for p in WENDY if "Amplification" in p.name]
    rep = import_files(amp)[0]
    r = rep.run.wells["A1"].reactions[0]
    assert r.cq is None and r.target == "SYBR" and len(r.amplification.x) == 40
    assert rep.run.instrument == "cfx" and rep.imported == 96


def test_folder_with_binary_and_stray_files(tmp_path):
    cq = next(p for p in WENDY if "Cq Results" in p.name)
    (tmp_path / cq.name).write_bytes(cq.read_bytes())
    (tmp_path / "run.pcrd").write_bytes(b"PK\x03\x04\x00\x00")
    (tmp_path / "notes.txt").write_text("hello lab\nthis is not a table\n", encoding="utf-8")
    reports = import_files([tmp_path])
    assert len(reports) == 1 and reports[0].imported == 96
    text = " ".join(reports[0].notes)
    assert "run.pcrd" in text and "notes.txt" in text


def test_only_binary_or_only_unknown_raise(tmp_path):
    p = tmp_path / "run.pcrd"
    p.write_bytes(b"PK\x03\x04\x00\x00")
    with pytest.raises(UnsupportedFileError):
        import_files([p])
    q = tmp_path / "g.csv"
    q.write_text("Pos,Gene,Ct\nA1,IL6,20\n", encoding="utf-8")
    with pytest.raises(UnknownFormatError):
        import_files([q])


def test_several_runs_numbered_from_index():
    reports = import_files([REAL / "BioRad_qPCR_melt.rdml"], first_run_index=3)
    assert [r.run.id for r in reports] == ["R3", "R4"]

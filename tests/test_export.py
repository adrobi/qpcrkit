import csv

import openpyxl
import pytest

from i18n import set_language, tr
from qpcr_core import __version__
from qpcr_core.export import export_csv, export_html, export_xlsx
from qpcr_core.pipeline import analyze
from tests.test_pipeline import demo_project

SHEETS = ["sheet.raw", "sheet.qc", "sheet.std", "sheet.abs", "sheet.rel", "sheet.stats", "sheet.params"]


@pytest.fixture(scope="module")
def data():
    set_language("en")
    p = demo_project()
    rxn = p.run("R1").wells["A2"].reactions[0]
    rxn.excluded, rxn.exclude_reason = True, "bubble"
    return p, analyze(p)


def test_xlsx_sheets_and_params(data, tmp_path):
    p, res = data
    path = tmp_path / "r.xlsx"
    export_xlsx(p, res, path)
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == [tr(k) for k in SHEETS]
    cells = [str(c.value) for row in wb[tr("sheet.params")].iter_rows() for c in row if c.value is not None]
    assert __version__ in cells
    assert any("A2" in c for c in cells) and "bubble" in cells
    raw = wb[tr("sheet.raw")]
    assert raw.max_row == 1 + sum(1 for _ in p.iter_reactions())


def test_csv(data, tmp_path):
    _, res = data
    path = tmp_path / "r.csv"
    export_csv(res, path)
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == ["sample", "group", "target", "mean_cq", "delta_cq", "rq", "log2_rq"]
    assert len(rows) == len(res.rqs)


def test_html(data, tmp_path):
    p, res = data
    path = tmp_path / "r.html"
    export_html(p, res, path)
    text = path.read_text(encoding="utf-8")
    assert "<svg" in text
    assert 'src="http' not in text
    assert "IL6" in text


def test_efficiency_source_reported(data, tmp_path):
    p, res = data
    path = tmp_path / "e.xlsx"
    export_xlsx(p, res, path)
    cells = [str(c.value) for row in openpyxl.load_workbook(path)[tr("sheet.params")].iter_rows() for c in row]
    assert "GAPDH: 1.0000 (ideal)" in cells
    assert any(c.startswith("IL6: ") and c.endswith("(stdcurve)") for c in cells)


# --- curves ---


@pytest.fixture
def curve_data():
    from tests.test_figures import _curve_project

    p = _curve_project()
    return p, analyze(p)


def test_curves_sheet(curve_data, tmp_path):
    p, res = curve_data
    path = tmp_path / "c.xlsx"
    export_xlsx(p, res, path)
    ws = openpyxl.load_workbook(path)[tr("sheet.curves")]
    rows = list(ws.iter_rows(values_only=True))
    col = {name: i for i, name in enumerate(rows[0])}
    by_well = {r[col["Well"]]: r for r in rows[1:]}
    assert {"Run", "Well", "Target", "Instrument Cq", "Cq from curve", "E", "Window R²", "Tm"} <= set(col)
    a1 = by_well["A1"]
    assert a1[col["Cq from curve"]] == pytest.approx(res.curves[("R1", "A1", "T", "FAM")].cq_calc)
    assert a1[col["E"]] == pytest.approx(res.curves[("R1", "A1", "T", "FAM")].efficiency)
    assert a1[col["Tm"]] == pytest.approx(84.0, abs=0.2)
    assert "B2" not in by_well  # no curve, no row


def test_no_curves_sheet_without_curves(data, tmp_path):
    p, res = data
    path = tmp_path / "c.xlsx"
    export_xlsx(p, res, path)
    assert tr("sheet.curves") not in openpyxl.load_workbook(path).sheetnames


def test_raw_sheet_has_our_values(curve_data, tmp_path):
    p, res = curve_data
    path = tmp_path / "c.xlsx"
    export_xlsx(p, res, path)
    rows = list(openpyxl.load_workbook(path)[tr("sheet.raw")].iter_rows(values_only=True))
    col = {name: i for i, name in enumerate(rows[0])}
    row = next(r for r in rows[1:] if r[col["Well"]] == "A1")
    assert row[col["Cq from curve"]] == pytest.approx(res.curves[("R1", "A1", "T", "FAM")].cq_calc)
    assert row[col["E"]] is not None and row[col["Tm"]] is not None


def test_html_has_curve_figures_and_tm(curve_data, tmp_path):
    p, res = curve_data
    path = tmp_path / "c.html"
    export_html(p, res, path)
    text = path.read_text(encoding="utf-8")
    assert text.count("<svg") >= 2
    assert tr("sheet.curves") in text
    assert "84." in text

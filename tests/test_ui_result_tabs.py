import pytest
from PySide6.QtCore import Qt

from qpcr_core.pipeline import Results, analyze
from tests.test_pipeline import demo_project
from ui.editor import ProjectEditor
from ui.result_tabs import ExpressionTab, QcTab, StdCurveTab


@pytest.fixture
def data():
    p = demo_project()
    return p, analyze(p)


def _empty():
    return Results([], {}, {}, {}, {}, {}, [], [], [], [])


def test_stdcurve_tab(qapp, data):
    p, res = data
    t = StdCurveTab()
    t.resize(800, 600)
    t.set_results(p, res, False)
    assert t.curve_count() == 1
    assert not t.grab().isNull()
    t.set_results(p, _empty(), True)
    assert t.curve_count() == 0 and not t.grab().isNull()


def test_expression_tab_error_bar_setting(qapp, data):
    p, res = data
    e = ProjectEditor(p)
    t = ExpressionTab(e)
    t.resize(800, 600)
    t.set_results(e.project, res, False)
    t.set_error_bar("sem")
    assert e.project.settings.error_bar == "sem"
    t.set_log2(True)
    assert not t.grab().isNull()
    t.set_results(e.project, _empty(), True)
    assert not t.grab().isNull()


def test_qc_tab_locate(qapp):
    p = demo_project()
    p.run("R1").wells["H1"].reactions[0].role = "ntc"
    p.run("R1").wells["H1"].reactions[0].cq = 30.0
    res = analyze(p)
    t = QcTab()
    t.set_results(p, res, False)
    hits = []
    t.locate.connect(lambda run_id, coord: hits.append((run_id, coord)))
    item = t.item_for_flag("ntc_contamination")
    t.tree.itemDoubleClicked.emit(item, 0)
    assert hits == [("R1", "H1")]
    assert not t.grab().isNull()
    t.set_results(p, _empty(), True)
    assert t.tree.topLevelItemCount() == 0


def test_stdcurve_table_shows_lowest_detected(qapp):
    from tests.factories import make_project
    from tests.test_stdcurve import _ideal_rows  # level 10 only partly detected

    p = make_project(_ideal_rows())
    res = analyze(p)
    t = StdCurveTab()
    t.set_results(p, res, False)
    assert t._table_widget.item(0, 6).text() == "100"


def test_stdcurve_keeps_selected_curve(qapp):
    from tests.factories import make_project
    from tests.test_stdcurve import _ideal_rows

    p = make_project(_ideal_rows(target="A") + _ideal_rows(target="B"))
    res = analyze(p)
    t = StdCurveTab()
    t.set_results(p, res, False)
    t._combo.setCurrentIndex(1)
    t.set_results(p, res, False)
    assert t._combo.currentIndex() == 1

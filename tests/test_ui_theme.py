from qpcr_core.figures import std_curve_figure
from qpcr_core.pipeline import analyze
from tests.test_pipeline import demo_project
from ui.theme import DARK, app_qss, mpl_style


def test_qss_differs_by_theme():
    assert app_qss(True) != app_qss(False)
    assert DARK["bg"] in app_qss(True)


def test_mpl_style():
    assert mpl_style(True)["figure.facecolor"] == DARK["bg"]


def test_canvas(qapp):
    from ui.canvas import FigureCanvas

    c = FigureCanvas()
    c.resize(400, 300)
    c.set_figure(std_curve_figure(analyze(demo_project()).std_curves[(None, "IL6")]))
    assert not c.grab().isNull()
    c.set_figure(None)
    assert not c.grab().isNull()

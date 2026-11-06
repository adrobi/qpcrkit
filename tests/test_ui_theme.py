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


def test_checkbox_indicator_styled():
    from ui.theme import LIGHT

    assert "QCheckBox::indicator" in app_qss(False) and LIGHT["accent"] in app_qss(False)


def test_resolve_dark():
    from ui.theme import resolve_dark

    assert resolve_dark("auto", True) is True
    assert resolve_dark("auto", False) is False
    assert resolve_dark("dark", False) is True
    assert resolve_dark("light", True) is False


def _checkbox_image(qapp, qss):
    from PySide6.QtWidgets import QCheckBox

    box = QCheckBox("x")
    box.setChecked(True)
    box.setStyleSheet(qss)
    box.resize(60, 24)
    return box.grab().toImage()


def test_checked_checkbox_has_tick(no_app_stylesheet):
    """Regression: a checked box must show a tick, not a plain accent square."""
    import re

    from PySide6.QtGui import QImageReader

    from ui.theme import LIGHT

    assert b"svg" in [bytes(f) for f in QImageReader.supportedImageFormats()]
    qss = app_qss(False)
    assert "QCheckBox::indicator:checked" in qss
    with_tick = _checkbox_image(no_app_stylesheet, qss)
    without = _checkbox_image(no_app_stylesheet, re.sub(r"image:\s*url\([^)]*\);?", "", qss))
    assert with_tick != without
    colors = {with_tick.pixelColor(x, y).name() for x in range(4, 13) for y in range(7, 17)}
    assert LIGHT["accent"] in colors and len(colors) >= 2


def test_controls_have_arrows():
    qss = app_qss(True)
    for rule in ("QComboBox::down-arrow", "QSpinBox::up-arrow", "QDoubleSpinBox::down-arrow"):
        assert rule in qss

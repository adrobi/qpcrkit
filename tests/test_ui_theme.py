import pytest

from qpcr_core.figures import std_curve_figure
from qpcr_core.pipeline import analyze
from tests.test_pipeline import demo_project
from ui.theme import DARK, LIGHT, app_qss, icon, mpl_style, resource_dir, theme


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


# --- the calm palette ---


def _contrast(a: str, b: str) -> float:
    def luminance(color: str) -> float:
        channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, bl = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * r + 0.7152 * g + 0.0722 * bl

    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("name", ["light", "dark"])
def test_text_is_readable(name):
    t = theme(name)
    for ink in ("text", "dim"):
        for paper in ("bg", "panel", "card"):
            assert _contrast(t[ink], t[paper]) >= 4.5, (ink, paper)
    assert _contrast(t["on_accent"], t["accent"]) >= 4.5
    assert _contrast(t["accent"], t["accent_soft"]) >= 3
    assert _contrast(t["warn"], t["panel"]) >= 3


def test_accent_is_the_one_from_the_spec():
    assert LIGHT["accent"] == "#0f766e"
    assert DARK["accent"] == "#2dd4bf"
    assert LIGHT.keys() == DARK.keys()


@pytest.mark.parametrize("dark", [False, True])
def test_stylesheet_covers_the_new_parts(dark):
    qss = app_qss(dark)
    for part in ("QScrollBar", "#navButton", "#chip", "#topBar", "#hintBar", "#navRail", "#startCard", "#primaryBtn", "QTableView"):
        assert part in qss, part
    assert (DARK if dark else LIGHT)["accent"] in qss
    assert "{t[" not in qss and "None" not in qss


@pytest.mark.parametrize(
    "name",
    ["grid-3x3", "table-2", "chart-scatter", "chart-column", "shield-check", "settings-2", "plus", "folder-open", "upload", "flask-conical", "rotate-ccw"],
)
def test_line_icons_are_there_and_take_a_color(qapp, name):
    assert not icon(name, "#0f766e").pixmap(16, 16).isNull()
    assert (resource_dir() / "icons" / f"{name}.svg").read_text(encoding="utf-8").count("currentColor") >= 1


def test_missing_icon_gives_an_empty_one(qapp):
    assert icon("no-such-icon", "#000000").isNull()

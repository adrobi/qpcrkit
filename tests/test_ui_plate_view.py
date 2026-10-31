from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from qpcr_core.models import format_coord
from tests.factories import make_project
from ui.plate_view import PlateView


def _project(fmt=96):
    rows = [("R1", format_coord(r, c), f"s{r}", "IL6", "unknown", 20.0 + c, None) for r in range(8) for c in range(12)]
    p = make_project(rows)
    p.runs[0].plate_format = fmt
    return p


def _view(p):
    v = PlateView()
    v.resize(900, 600)
    v.set_run(p.runs[0], p)
    v.show()
    return v


def test_renders(qapp):
    v = _view(_project())
    assert not v.grab().isNull()


def test_select_coords_emits(qapp):
    v = _view(_project())
    hits = []
    v.selection_changed.connect(lambda: hits.append(1))
    v.select_coords(["B2", "A1"])
    assert v.selected_coords() == ["A1", "B2"]
    assert hits


def test_row_header_click_selects_row(qapp):
    v = _view(_project())
    rect = v.header_rect("row", 1)
    QTest.mouseClick(v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, rect.center())
    assert v.selected_coords() == [format_coord(1, c) for c in range(12)]


def test_column_header_click_selects_column(qapp):
    v = _view(_project())
    QTest.mouseClick(v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, v.header_rect("col", 0).center())
    assert v.selected_coords() == [format_coord(r, 0) for r in range(8)]


def test_rotor_gene_run(qapp):
    p = make_project([("R1", str(i), "s", "Green", "unknown", 20.0, None) for i in range(1, 73)])
    p.runs[0].plate_format = 72
    v = _view(p)
    v.select_coords(["13", "2"])
    assert v.selected_coords() == ["2", "13"]
    assert not v.grab().isNull()


def test_excluded_and_modes(qapp):
    p = _project()
    p.runs[0].wells["A1"].reactions[0].excluded = True
    v = _view(p)
    v.set_color_mode("role")
    v.set_theme(True)
    assert not v.grab().isNull()


def test_empty(qapp):
    v = PlateView()
    v.set_run(None, None)
    assert not v.grab().isNull()

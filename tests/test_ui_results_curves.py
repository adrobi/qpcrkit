"""Data columns from curves, excluding a standard by clicking it, saving figures."""

from __future__ import annotations

import pytest
from matplotlib.backend_bases import MouseButton, MouseEvent
from matplotlib.colors import to_hex
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from qpcr_core.figures import expression_figure, std_curve_figure
from qpcr_core.pipeline import analyze
from tests.curve_factory import logistic, melt
from tests.test_curve_pipeline import _project
from tests.test_pipeline import demo_project
from ui.data_table import COLUMNS, DataTable, ReactionModel
from ui.editor import ProjectEditor
from ui.theme import mpl_style


# --- the data table ---


def _model():
    rows = [("R1", f"A{i + 1}", f"s{i}", "T", "unknown", 20.0 + i, logistic(30 - i, seed=i, noise=0.002), melt(tm=84.0)) for i in range(5)]
    rows.append(("R1", "B1", "x", "T", "unknown", 22.0, None))
    p = _project(rows)
    e = ProjectEditor(p)
    m = ReactionModel(e)
    m.set_results(analyze(p))
    return e, m


def _cell(m, row, name, role=Qt.ItemDataRole.DisplayRole):
    return m.data(m.index(row, COLUMNS.index(name)), role)


def test_new_columns_are_last():
    assert COLUMNS[-3:] == ("cq_calc", "efficiency", "tm")


def test_columns_show_the_results(qapp):
    _, m = _model()
    res = analyze(m.editor.project).curves[("R1", "A1", "T", "FAM")]
    assert _cell(m, 0, "cq_calc") == f"{res.cq_calc:.2f}"
    assert _cell(m, 0, "efficiency") == f"{res.efficiency:.1%}"
    assert _cell(m, 0, "tm") == f"{res.tms[0]:.1f}"


def test_columns_empty_without_a_curve(qapp):
    _, m = _model()
    assert _cell(m, 5, "cq_calc") == "—"
    assert _cell(m, 5, "efficiency") == "" and _cell(m, 5, "tm") == ""


def test_columns_empty_without_results(qapp):
    e = ProjectEditor(demo_project())
    m = ReactionModel(e)
    assert _cell(m, 0, "cq_calc") == "—"


def test_columns_are_read_only(qapp):
    _, m = _model()
    for name in COLUMNS[-3:]:
        assert not m.flags(m.index(0, COLUMNS.index(name))) & Qt.ItemFlag.ItemIsEditable


def test_columns_sort_as_numbers(qapp):
    from ui.data_table import SORT_ROLE

    _, m = _model()
    assert isinstance(_cell(m, 0, "cq_calc", SORT_ROLE), float)
    assert _cell(m, 5, "cq_calc", SORT_ROLE) == float("inf")
    assert _cell(m, 0, "tm", SORT_ROLE) == pytest.approx(84.0, abs=0.2)


def test_new_results_refresh_the_columns(qapp):
    _, m = _model()
    got = []
    m.dataChanged.connect(lambda *a: got.append(1))
    m.set_results(None)
    assert got and _cell(m, 0, "cq_calc") == "—"


def test_columns_have_titles(qapp):
    from i18n import tr

    _, m = _model()
    for name in COLUMNS[-3:]:
        assert m.headerData(COLUMNS.index(name), Qt.Orientation.Horizontal) == tr(f"ui.col.{name}")


def test_table_filter_still_works_with_the_new_columns(qapp):
    e, _ = _model()
    t = DataTable(e)
    t.set_filter("A1")
    assert t.visible_row_count() == 1


def test_window_passes_results_to_the_table(win):
    rows = [("R1", f"A{i + 1}", f"s{i}", "T", "unknown", 20.0, logistic(25, seed=i, noise=0.002)) for i in range(3)]
    win.editor.set_project(_project(rows))
    win.recalculate_now()
    m = win.data.model
    assert _cell(m, 0, "cq_calc") not in ("—", None)


# --- excluding a standard on its curve ---


def _click_point(tab, index):
    canvas = tab._canvas.mpl_canvas
    canvas.draw()
    curve = tab._curves[tab._combo.currentIndex()][1]
    point = curve.points[index]
    x, y = canvas.figure.axes[0].transData.transform((point.quantity, point.cq))
    MouseEvent("button_press_event", canvas, x, y, button=MouseButton.LEFT)._process()
    MouseEvent("button_release_event", canvas, x, y, button=MouseButton.LEFT)._process()
    return point


def test_click_on_a_point_names_its_well(demo):
    demo.std.resize(800, 600)
    got = []
    demo.std.point_clicked.connect(lambda *a: got.append(a))
    point = _click_point(demo.std, 0)
    assert got and got[0] == (point.run_id, point.coord, "IL6")


def test_click_past_the_points_does_nothing(demo):
    got = []
    demo.std.point_clicked.connect(lambda *a: got.append(a))
    canvas = demo.std._canvas.mpl_canvas
    canvas.draw()
    box = canvas.figure.axes[0].bbox
    MouseEvent("button_press_event", canvas, box.x0 + 2, box.y0 + 2, button=MouseButton.LEFT)._process()
    assert got == []


def test_window_excludes_the_reaction_of_that_target_only(demo):
    curve = demo.results.std_curves[(None, "IL6")]
    before = len(curve.points)
    point = _click_point(demo.std, 0)
    rxns = demo.editor.project.run(point.run_id).wells[point.coord].reactions
    assert [r.excluded for r in rxns if r.target == "IL6"] == [True]
    assert point.coord in demo.statusBar().currentMessage()
    demo.recalculate_now()
    assert point.coord in demo.statusBar().currentMessage()  # the recalculation does not wipe the note
    assert len(demo.results.std_curves[(None, "IL6")].points) == before - 1


def test_undo_returns_the_point(demo):
    before = len(demo.results.std_curves[(None, "IL6")].points)
    _click_point(demo.std, 0)
    demo.editor.undo()
    demo.recalculate_now()
    assert len(demo.results.std_curves[(None, "IL6")].points) == before


# --- saving the figure ---


def test_save_button_gives_a_white_figure_in_the_dark_theme(demo, tmp_path, monkeypatch):
    demo.apply_theme("dark", save=False)
    path = tmp_path / "fig.png"
    monkeypatch.setattr(demo, "_ask_save_path", lambda *a: str(path))
    demo.expr.save_button.click()
    image = QImage(str(path))
    assert not image.isNull()
    assert image.pixelColor(2, 2).name() == "#ffffff"
    demo.apply_theme("light", save=False)


def test_cancelled_save_writes_nothing(demo, monkeypatch):
    monkeypatch.setattr(demo, "_ask_save_path", lambda *a: None)
    demo.expr.save_button.click()
    assert not demo.errors


def test_failed_save_says_so(demo, tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "_ask_save_path", lambda *a: str(tmp_path / "fig.xyz"))
    demo.expr.save_button.click()
    assert demo.errors


def test_save_button_is_off_without_a_figure(win):
    assert not win.expr.save_button.isEnabled()


# --- figures on a dark background ---


def test_lines_follow_the_style(qapp):
    res = analyze(demo_project())
    style = mpl_style(True)
    ink = style["text.color"]
    fig = std_curve_figure(res.std_curves[(None, "IL6")], style=style)
    assert to_hex(fig.axes[0].lines[0].get_color()) == ink
    fig = expression_figure(res, "IL6", style=style)
    dots = fig.axes[0].collections[-1]
    assert to_hex(dots.get_facecolor()[0]) == ink


def test_export_keeps_its_colors(qapp):
    res = analyze(demo_project())
    fig = std_curve_figure(res.std_curves[(None, "IL6")])
    assert to_hex(fig.axes[0].lines[0].get_color()) == to_hex("0.3")


# --- export of figures with curves ---


def test_export_figures_has_the_curves(win, tmp_path):
    rows = [("R1", f"A{i + 1}", f"s{i}", "T", "unknown", 20.0, logistic(25, seed=i, noise=0.002), melt()) for i in range(3)]
    win.editor.set_project(_project(rows))
    win.recalculate_now()
    assert win.export("figures", tmp_path)
    assert list(tmp_path.glob("amplification_*.svg")) and list(tmp_path.glob("melt_*.svg"))


# --- what the screenshots showed ---


def test_standard_curve_figure_gets_most_of_the_page(demo):
    from PySide6.QtWidgets import QApplication

    demo.go_to("std")
    demo.resize(1400, 860)
    demo.show()
    QApplication.processEvents()
    figure, table = demo.std.splitter.sizes()
    assert figure >= 2 * table
    demo.hide()


def test_result_tables_fill_their_width_and_have_no_row_numbers(demo):
    for table in (demo.std._table_widget, demo.expr._groups_table, demo.expr._comparisons_table):
        assert table.horizontalHeader().stretchLastSection()
        assert not table.verticalHeader().isVisible()


def test_settings_dialog_has_no_sideways_scrolling(win):
    from PySide6.QtWidgets import QScrollArea

    area = win.analysis.panel.findChild(QScrollArea)
    assert area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert win.analysis.width() >= 600


def test_efficiency_modes_say_what_they_are_from(win):
    from i18n import tr

    assert tr("ui.eff.stdcurve") != tr("ui.eff.curves")


def test_role_field_says_it_is_a_role(win):
    from i18n import tr

    assert win.selection.role_combo.itemText(0) == tr("ui.role_keep")

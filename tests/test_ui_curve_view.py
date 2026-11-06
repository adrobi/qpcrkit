"""The curve graph beside the plate."""

from __future__ import annotations

import io

import numpy as np
import pytest
from matplotlib.backend_bases import MouseButton, MouseEvent

from i18n import tr
from qpcr_core.curves import melt_derivative
from qpcr_core.pipeline import analyze
from tests.curve_factory import flat, logistic, melt
from tests.test_curve_pipeline import _project
from ui.curve_view import CurveView


def _rows():
    rows = [
        ("R1", f"A{i + 1}", f"s{i}", "T", "unknown", None, logistic(20 + 2 * i, seed=i, noise=0.002), melt(tm=84.0))
        for i in range(4)
    ]
    rows.append(("R1", "B1", "x", "U", "unknown", None, logistic(26, plateau=1.0, threshold=0.05)))
    rows.append(("R1", "B2", "x", "U", "unknown", None, flat(noise=0.002)))
    return rows


@pytest.fixture(autouse=True)
def no_leftover_views(qapp):
    """A canvas that outlives QApplication crashes the interpreter on exit."""
    from PySide6.QtCore import QCoreApplication, QEvent

    yield
    for widget in qapp.topLevelWidgets():
        if isinstance(widget, CurveView):
            widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def view(qapp):
    p = _project(_rows())
    v = CurveView()
    v.resize(700, 500)
    v.set_data(p, analyze(p), "R1")
    v.canvas.draw()
    return v


def _point(v, x, y):
    """Display coordinates of a data point, as matplotlib events use them."""
    return v.ax.transData.transform((x, y))


def _click(v, x_px, y_px, **kw):
    MouseEvent("button_press_event", v.canvas, x_px, y_px, button=MouseButton.LEFT, **kw)._process()
    MouseEvent("button_release_event", v.canvas, x_px, y_px, button=MouseButton.LEFT, **kw)._process()


def _on_curve(v, coord, cycle=21):  # on the rise, where the curves are apart
    from qpcr_core.curves import subtracted_curve

    well = v.project.run("R1").wells[coord]
    c = subtracted_curve(well.reactions[0])
    return _point(v, c.x[cycle], c.y[cycle])


# --- what is drawn ---


def test_one_line_per_curve(view):
    assert view.line_count() == 6


def test_filter_by_target(view):
    view.target_combo.setCurrentIndex(view.target_combo.findData("T"))
    assert view.line_count() == 4
    view.target_combo.setCurrentIndex(view.target_combo.findData("U"))
    assert view.line_count() == 2
    view.target_combo.setCurrentIndex(view.target_combo.findData(""))
    assert view.line_count() == 6


def test_melt_mode_draws_melt_curves(view):
    view.mode_combo.setCurrentIndex(view.mode_combo.findData("melt"))
    assert view.line_count() == 4


def test_ready_derivative_is_drawn_too(qapp):
    p = _project([("R1", "A1", "s", "T", "unknown", 22.0, None)])
    p.runs[0].wells["A1"].reactions[0].melt_derivative = melt_derivative(melt(tm=80.0))
    v = CurveView()
    v.set_data(p, analyze(p), "R1")
    v.mode_combo.setCurrentIndex(v.mode_combo.findData("melt"))
    assert v.line_count() == 1


def test_excluded_reactions_are_not_drawn(qapp):
    p = _project(_rows())
    p.runs[0].wells["A1"].reactions[0].excluded = True
    v = CurveView()
    v.set_data(p, analyze(p), "R1")
    assert v.line_count() == 5


def test_log_scale_with_non_positive_values(view):
    view.mode_combo.setCurrentIndex(view.mode_combo.findData("log"))
    assert view.ax.get_yscale() == "log"
    assert view.ax.get_ylim()[0] > 0
    view.figure.savefig(io.BytesIO(), format="png")
    view.mode_combo.setCurrentIndex(view.mode_combo.findData("amp"))
    assert view.ax.get_yscale() == "linear"


# --- selection ---


def test_selection_draws_a_top_layer_and_keeps_the_axes(view):
    limits = view.ax.get_xlim(), view.ax.get_ylim()
    view.set_selection(["A1"])
    assert view.selected_line_count() == 1
    assert (view.ax.get_xlim(), view.ax.get_ylim()) == limits
    view.set_selection(["A1", "A2"])
    assert view.selected_line_count() == 2
    view.set_selection([])
    assert view.selected_line_count() == 0


def test_selection_dims_the_other_curves(view):
    assert view.layer_alpha() == 1.0
    view.set_selection(["A1"])
    assert view.layer_alpha() == pytest.approx(0.25)
    view.set_selection([])
    assert view.layer_alpha() == 1.0


def test_selection_changes_the_picture(view):
    before = np.asarray(view.canvas.buffer_rgba()).copy()
    view.set_selection(["A1"])
    view.canvas.draw()
    assert (np.asarray(view.canvas.buffer_rgba()) != before).any()


def test_selection_of_an_unknown_well_is_harmless(view):
    view.set_selection(["P24"])
    assert view.selected_line_count() == 0


def test_set_selection_does_not_report_a_click(view):
    got = []
    view.wells_clicked.connect(lambda *a: got.append(a))
    view.set_selection(["A1"])
    assert got == []


def test_selection_survives_new_data(view):
    view.set_selection(["A2"])
    view.set_data(view.project, view.results, "R1")
    assert view.selected_line_count() == 1


# --- clicks ---


def test_coord_at_finds_the_curve(view):
    x, y = _on_curve(view, "A1")
    assert view.coord_at(x, y) == "A1"


def test_coord_at_between_cycles(view):
    a = _on_curve(view, "A1", 21)
    b = _on_curve(view, "A1", 22)
    assert view.coord_at((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) == "A1"


def test_coord_at_far_from_curves(view):
    box = view.ax.bbox
    assert view.coord_at(box.x0 + 2, box.y1 - 2) is None


def test_click_reports_the_well(view):
    got = []
    view.wells_clicked.connect(lambda coords, add: got.append((coords, add)))
    _click(view, *_on_curve(view, "A1"))
    assert got == [(["A1"], False)]


def test_ctrl_click_adds(view):
    got = []
    view.wells_clicked.connect(lambda coords, add: got.append((coords, add)))
    _click(view, *_on_curve(view, "A1"), modifiers=frozenset({"ctrl"}))
    assert got == [(["A1"], True)]


def test_click_past_the_curves_reports_nothing(view):
    got = []
    view.wells_clicked.connect(lambda *a: got.append(a))
    box = view.ax.bbox
    _click(view, box.x0 + 2, box.y1 - 2)
    assert got == []


def test_hover_text(view):
    text = view.hover_text("A1")
    assert "A1" in text and "s0" in text and "T" in text and "Cq" in text


# --- no curves, another run ---


def test_run_without_curves_says_so(qapp):
    p = _project([("R1", "A1", "s", "T", "unknown", 25.0, None)])
    v = CurveView()
    v.set_data(p, analyze(p), "R1")
    assert v.line_count() == 0
    assert v.placeholder.text() == tr("ui.curves.none")
    assert not v.placeholder.isHidden() and v.canvas.isHidden()
    v.set_selection(["A1"])  # nothing to draw, nothing to fail
    assert v.coord_at(10, 10) is None


def test_no_run_at_all(qapp):
    v = CurveView()
    v.set_data(None, None, None)
    assert v.line_count() == 0


def test_target_of_another_run_falls_back_to_all(qapp):
    rows = _rows() + [("R2", "A1", "s", "Z", "unknown", None, logistic(25))]
    p = _project(rows)
    res = analyze(p)
    v = CurveView()
    v.set_data(p, res, "R1")
    v.target_combo.setCurrentIndex(v.target_combo.findData("T"))
    v.set_data(p, res, "R2")
    assert v.target_combo.currentData() == "" and v.line_count() == 1
    assert v.target_combo.findData("T") == -1


def test_chosen_target_stays_when_the_data_refresh(view):
    view.target_combo.setCurrentIndex(view.target_combo.findData("T"))
    view.set_data(view.project, view.results, "R1")
    assert view.target_combo.currentData() == "T" and view.line_count() == 4


def test_theme_changes_the_background(view):
    light = view.figure.get_facecolor()
    view.set_theme(True)
    assert view.figure.get_facecolor() != light
    view.canvas.draw()


# --- inside the window ---


@pytest.fixture
def curve_win(win):
    from qpcr_core.models import Project

    p = _project(_rows())
    win.editor.set_project(p)
    win.recalculate_now()
    win.curves.canvas.draw()
    return win


def test_window_links_plate_to_curves(curve_win):
    curve_win.plate.select_coords(["A2"])
    assert curve_win.curves.selected_line_count() == 1


def test_window_links_curves_to_plate(curve_win):
    v = curve_win.curves
    _click(v, *_on_curve(v, "A1"))
    assert curve_win.plate.selected_coords() == ["A1"]
    assert "1" in curve_win.selection.label.text()
    assert v.selected_line_count() == 1


def test_ctrl_click_adds_and_removes_in_the_window(curve_win):
    v = curve_win.curves
    curve_win.plate.select_coords(["A2"])
    _click(v, *_on_curve(v, "A1"), modifiers=frozenset({"ctrl"}))
    assert curve_win.plate.selected_coords() == ["A1", "A2"]
    _click(v, *_on_curve(v, "A1"), modifiers=frozenset({"ctrl"}))
    assert curve_win.plate.selected_coords() == ["A2"]


def test_recalculation_keeps_the_selection(curve_win):
    curve_win.plate.select_coords(["A2"])
    curve_win.recalculate_now()
    assert curve_win.plate.selected_coords() == ["A2"] and curve_win.curves.selected_line_count() == 1


def test_selection_does_not_analyze(curve_win, monkeypatch):
    import ui.main_window as mw

    calls = []
    monkeypatch.setattr(mw, "analyze", lambda p: calls.append(1))
    curve_win.plate.select_coords(["A1", "A2"])
    _click(curve_win.curves, *_on_curve(curve_win.curves, "A3"))
    assert calls == [] and not curve_win._timer.isActive()


def test_other_run_in_the_window(win):
    p = _project(_rows() + [("R2", "A1", "s", "Z", "unknown", None, logistic(25))])
    win.editor.set_project(p)
    win.recalculate_now()
    win.select_run("R2")
    assert win.curves.line_count() == 1


# --- the threshold ---


def _event(v, name, x, y):
    MouseEvent(name, v.canvas, x, y, button=MouseButton.LEFT)._process()


def _drag(v, to_data_y):
    """Press on the line, move to a level of the data, release there."""
    box = v.ax.bbox
    x = (box.x0 + box.x1) / 2
    y0 = v.ax.transData.transform((1, v.threshold_value()))[1]
    y1 = v.ax.transData.transform((1, to_data_y))[1]
    _event(v, "button_press_event", x, y0)
    _event(v, "motion_notify_event", x, y1)
    _event(v, "button_release_event", x, y1)


def _single(v):
    v.target_combo.setCurrentIndex(v.target_combo.findData("T"))
    v.canvas.draw()
    return v


def test_line_only_with_one_target(view):
    assert view.threshold_line is None
    assert _single(view).threshold_line is not None


def test_line_on_a_run_with_a_single_target(qapp):
    p = _project([("R1", f"A{i + 1}", f"s{i}", "T", "unknown", None, logistic(20 + i)) for i in range(3)])
    v = CurveView()
    v.resize(700, 500)
    v.set_data(p, analyze(p), "R1")
    assert v.threshold_line is not None


def test_no_line_on_melt(view):
    _single(view)
    view.mode_combo.setCurrentIndex(view.mode_combo.findData("melt"))
    assert view.threshold_line is None
    view.mode_combo.setCurrentIndex(view.mode_combo.findData("log"))
    assert view.threshold_line is not None


def test_no_line_without_a_threshold(qapp):
    p = _project([("R1", "A1", "s", "T", "ntc", None, flat(noise=0.002))])
    v = CurveView()
    v.resize(700, 500)
    v.set_data(p, analyze(p), "R1")
    assert v.threshold_line is None


def test_line_shows_the_threshold_of_the_results(view):
    _single(view)
    expected = view.results.curves[("R1", "A1", "T", "FAM")].threshold
    assert view.threshold_value() == pytest.approx(expected)


def test_line_prefers_the_manual_value(view):
    _single(view)
    view.project.runs[0].thresholds["T"] = 0.33
    view.set_data(view.project, view.results, "R1")
    assert view.threshold_value() == pytest.approx(0.33)


def test_drag_reports_the_new_value(view):
    _single(view)
    got = []
    clicks = []
    view.threshold_changed.connect(lambda t, value: got.append((t, value)))
    view.wells_clicked.connect(lambda *a: clicks.append(a))
    _drag(view, 0.5)
    assert len(got) == 1 and got[0][0] == "T"
    assert got[0][1] == pytest.approx(0.5, rel=0.03)
    assert clicks == []


def test_drag_moves_the_line_while_moving(view):
    _single(view)
    box = view.ax.bbox
    x = (box.x0 + box.x1) / 2
    y0 = view.ax.transData.transform((1, view.threshold_value()))[1]
    y1 = view.ax.transData.transform((1, 0.6))[1]
    _event(view, "button_press_event", x, y0)
    _event(view, "motion_notify_event", x, y1)
    assert view.threshold_value() == pytest.approx(0.6, rel=0.03)
    _event(view, "button_release_event", x, y1)


def test_press_elsewhere_does_not_drag(view):
    _single(view)
    got = []
    view.threshold_changed.connect(lambda *a: got.append(a))
    box = view.ax.bbox
    x = (box.x0 + box.x1) / 2
    far = view.ax.transData.transform((1, view.threshold_value()))[1] + 60
    _event(view, "button_press_event", x, far)
    _event(view, "motion_notify_event", x, far + 20)
    _event(view, "button_release_event", x, far + 20)
    assert got == []


def test_release_below_zero_puts_the_line_back(view):
    _single(view)
    before = view.threshold_value()
    got = []
    view.threshold_changed.connect(lambda *a: got.append(a))
    _drag(view, view.ax.get_ylim()[0] * 0.5)  # the axis goes a little below zero
    assert got == []
    assert view.threshold_value() == pytest.approx(before)


def test_release_outside_the_axes_puts_the_line_back(view):
    _single(view)
    before = view.threshold_value()
    got = []
    view.threshold_changed.connect(lambda *a: got.append(a))
    box = view.ax.bbox
    x = (box.x0 + box.x1) / 2
    y0 = view.ax.transData.transform((1, before))[1]
    _event(view, "button_press_event", x, y0)
    _event(view, "motion_notify_event", x, y0 + 30)
    _event(view, "button_release_event", box.x1 + 40, y0 + 30)
    assert got == []
    assert view.threshold_value() == pytest.approx(before)


def test_drag_on_a_log_axis(view):
    _single(view)
    view.mode_combo.setCurrentIndex(view.mode_combo.findData("log"))
    view.canvas.draw()
    got = []
    view.threshold_changed.connect(lambda t, value: got.append(value))
    _drag(view, 0.05)
    assert got and got[0] == pytest.approx(0.05, rel=0.1)


def test_auto_button_only_with_a_manual_threshold(view):
    _single(view)
    assert view.auto_button.isHidden()
    view.project.runs[0].thresholds["T"] = 0.33
    view.set_data(view.project, view.results, "R1")
    assert not view.auto_button.isHidden()
    got = []
    view.threshold_reset.connect(got.append)
    view.auto_button.click()
    assert got == ["T"]


def test_auto_button_hidden_with_several_targets(view):
    view.project.runs[0].thresholds["T"] = 0.33
    view.set_data(view.project, view.results, "R1")
    assert view.auto_button.isHidden()


def test_window_applies_a_dragged_threshold_at_once(curve_win):
    v = curve_win.curves
    _single(v)
    key = ("R1", "A1", "T", "FAM")
    before = curve_win.results.curves[key]
    _drag(v, 0.5)
    v = curve_win.curves
    project = curve_win.editor.project
    assert project.runs[0].thresholds["T"] == pytest.approx(0.5, rel=0.03)
    assert not curve_win._timer.isActive()
    after = curve_win.results.curves[key]
    assert after.threshold == pytest.approx(0.5, rel=0.03)
    assert after.cq_calc > before.cq_calc
    assert v.threshold_value() == pytest.approx(0.5, rel=0.03)


def test_window_undo_returns_the_line(curve_win):
    v = curve_win.curves
    _single(v)
    before = v.threshold_value()
    _drag(v, 0.5)
    curve_win.editor.undo()
    curve_win.recalculate_now()
    assert curve_win.editor.project.runs[0].thresholds == {}
    assert v.threshold_value() == pytest.approx(before)
    assert v.auto_button.isHidden()


def test_window_auto_button_goes_back(curve_win):
    v = curve_win.curves
    _single(v)
    before = v.threshold_value()
    _drag(v, 0.5)
    assert not v.auto_button.isHidden()
    v.auto_button.click()
    assert curve_win.editor.project.runs[0].thresholds == {}
    assert v.threshold_value() == pytest.approx(before)

"""Findings of the final review, each reproduced first."""

from __future__ import annotations

from pathlib import Path

import pytest
from matplotlib.backend_bases import MouseButton, MouseEvent
from shiboken6 import isValid

from i18n import tr
from qpcr_core.editing import set_target_kind
from qpcr_core.models import Project, Reaction, Run, Well
from qpcr_core.pipeline import analyze
from qpcr_core.stdcurve import fit_std_curves
from tests.conftest import RUN1
from tests.curve_factory import logistic
from tests.factories import make_project
from tests.test_curve_pipeline import _project
from tests.test_ui_curve_view import _event, _single, no_leftover_views, view  # noqa: F401
from ui.editor import ProjectEditor
from ui.shell import TopBar


# --- empty wells in the selection ---


def _partial_plate(win):
    win.add_run(RUN1)
    run = win.editor.project.runs[0]
    assert "H12" not in run.wells  # the demo plate is not full
    return run


def test_apply_with_empty_wells_selected(win):
    run = _partial_plate(win)
    present = next(iter(run.wells))
    win.plate.select_coords([present, "H12"])
    win.selection.sample_edit.setText("New")
    win.selection.apply_button.click()
    assert run.wells[present].sample == "New" and "H12" not in run.wells


def test_series_and_exclusion_with_empty_wells_selected(win):
    run = _partial_plate(win)
    present = next(iter(run.wells))
    win.plate.select_coords([present, "H12"])
    win.fill_series_selected("S", 1)
    assert run.wells[present].sample == "S1"
    win._set_selection_excluded(True)
    assert run.wells[present].reactions[0].excluded


def test_only_empty_wells_selected_does_nothing(win):
    _partial_plate(win)
    win.editor.mark_saved(Path("x"))
    win.plate.select_coords(["H12"])
    win.selection.sample_edit.setText("New")
    win.selection.apply_button.click()
    assert not win.editor.dirty


# --- what cannot be imported ---


def test_drop_an_empty_folder(win, tmp_path):
    assert win.add_run([tmp_path]) is False
    assert win.errors and win.is_start_shown()


def test_wizard_is_not_offered_for_several_unknown_files(win, tmp_path, monkeypatch):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("x,y\n1,2\n", encoding="utf-8")
    b.write_text("p,q\n3,4\n", encoding="utf-8")
    asked = []
    monkeypatch.setattr(win, "_run_wizard", lambda rows: asked.append(rows))
    assert win.add_run([a, b]) is False
    assert asked == [] and win.errors


# --- quantity ---


@pytest.mark.parametrize("bad", ["abc", "nan", "inf", "-5", "0"])
def test_bad_quantity_is_refused_and_kept(win, bad):
    run = _partial_plate(win)
    present = next(iter(run.wells))
    win.editor.mark_saved(Path("x"))
    win.plate.select_coords([present])
    win.selection.quantity_edit.setText(bad)
    win.selection.apply_button.click()
    assert not win.editor.dirty
    assert win.selection.quantity_edit.text() == bad
    assert win.statusBar().currentMessage() == tr("ui.bad_quantity")


def test_apply_with_empty_fields_leaves_no_step(win):
    run = _partial_plate(win)
    win.plate.select_coords([next(iter(run.wells))])
    win.editor.mark_saved(Path("x"))
    undoable = win.editor.can_undo
    win.selection.apply_button.click()
    assert not win.editor.dirty and win.editor.can_undo == undoable


def test_nan_quantity_in_a_file_does_not_reach_the_curve():
    rows = [("R1", f"A{i}", None, "T", "std", 30.0 - 3.3 * i, 10.0 ** i) for i in range(1, 5)]
    p = make_project(rows)
    p.runs[0].wells["A1"].reactions[0].quantity = float("nan")
    curves, flags = fit_std_curves(p, lambda run, well, rxn: rxn.cq)
    assert curves[(None, "T")].n_points == 3
    assert "std_no_quantity" in [f.code for f in flags]


# --- a standard excluded by a click ---


def _point_event(demo, button=MouseButton.LEFT):
    canvas = demo.std._canvas.mpl_canvas
    canvas.draw()
    p = demo.results.std_curves[(None, "IL6")].points[0]
    x, y = canvas.figure.axes[0].transData.transform((p.quantity, p.cq))
    MouseEvent("button_press_event", canvas, x, y, button=button)._process()


def test_exclusion_shows_at_once(demo):
    before = len(demo.results.std_curves[(None, "IL6")].points)
    _point_event(demo)
    assert len(demo.results.std_curves[(None, "IL6")].points) == before - 1
    assert not demo._timer.isActive()


def test_right_button_does_not_exclude(demo):
    before = len(demo.results.std_curves[(None, "IL6")].points)
    _point_event(demo, MouseButton.RIGHT)
    assert len(demo.results.std_curves[(None, "IL6")].points) == before


def test_one_undo_returns_two_quick_clicks_one_by_one(demo):
    before = len(demo.results.std_curves[(None, "IL6")].points)
    _point_event(demo)
    _point_event(demo)
    assert len(demo.results.std_curves[(None, "IL6")].points) == before - 2
    demo.editor.undo()
    demo.recalculate_now()
    assert len(demo.results.std_curves[(None, "IL6")].points) == before - 1


# --- the threshold during a recalculation ---


def test_recalculation_during_a_drag_does_not_lose_it(view):  # noqa: F811
    _single(view)
    got = []
    view.threshold_changed.connect(lambda t, value: got.append(value))
    box = view.ax.bbox
    x = (box.x0 + box.x1) / 2
    y0 = view.ax.transData.transform((1, view.threshold_value()))[1]
    y1 = view.ax.transData.transform((1, 0.5))[1]
    _event(view, "button_press_event", x, y0)
    _event(view, "motion_notify_event", x, y1)
    view.set_data(view.project, view.results, "R1")  # the delayed recalculation fires
    assert view.threshold_value() == pytest.approx(0.5, rel=0.03)
    y2 = view.ax.transData.transform((1, 0.6))[1]
    _event(view, "motion_notify_event", x, y2)
    _event(view, "button_release_event", x, y2)
    assert got and got[0] == pytest.approx(0.6, rel=0.03)


def test_line_gone_during_a_drag_ends_it(view):  # noqa: F811
    _single(view)
    box = view.ax.bbox
    x = (box.x0 + box.x1) / 2
    y0 = view.ax.transData.transform((1, view.threshold_value()))[1]
    _event(view, "button_press_event", x, y0)
    view.mode_combo.setCurrentIndex(view.mode_combo.findData("melt"))
    _event(view, "motion_notify_event", x, y0 + 20)
    _event(view, "button_release_event", x, y0 + 20)
    assert view.threshold_line is None


# --- chips ---


def _bar(project):
    e = ProjectEditor(project)
    bar = TopBar(e)
    bar.refresh(project, None)
    e.changed.connect(lambda: bar.refresh(e.project, None))  # as the window does
    return e, bar


def _named(*targets):
    p = Project(runs=[Run(id="R", name="R", wells={f"A{i}": Well(f"A{i}", "s", [Reaction(target=t)]) for i, t in enumerate(targets)})])
    p.ensure_targets_and_samples()
    return p


def test_action_outlives_its_own_signal(qapp):
    e, bar = _bar(_named("T"))
    action = bar.ref_chip.menu().actions()[0]
    action.trigger()  # the refresh runs inside this call
    assert isValid(action)
    assert e.project.targets["T"].kind == "reference"


def test_ampersand_in_a_name_is_shown_as_it_is(qapp):
    e, bar = _bar(_named("A&B"))
    action = bar.ref_chip.menu().actions()[0]
    assert action.text() == "A&&B"
    action.trigger()
    assert e.project.targets["A&B"].kind == "reference"
    assert "A&&B" in bar.ref_chip.text()


def test_group_with_an_ampersand(qapp):
    p = _named("T")
    p.samples["s"].group = "LPS & Dex"
    e, bar = _bar(p)
    bar.control_chip.menu().actions()[0].trigger()
    assert e.project.settings.control_group == "LPS & Dex"
    assert "LPS && Dex" in bar.control_chip.text()


def test_second_click_on_the_chosen_group_unsets_it(qapp):
    p = _named("T")
    p.samples["s"].group = "Ctrl"
    p.settings.control_group = "Ctrl"
    e, bar = _bar(p)
    bar.control_chip.menu().actions()[0].trigger()
    assert e.project.settings.control_group == ""


# --- another project ---


def test_new_project_forgets_the_old_one(demo, tmp_path):
    from qpcr_core.sessions import save_project

    path = tmp_path / "other.qpcrkit.json"
    other = make_project([("R1", "A1", "s", "T", "unknown", 20.0, None)])
    save_project(other, path)
    demo.select_run("R2")
    demo.plate.select_coords(["A1", "A2"])
    demo.selection.sample_edit.setText("typed")
    demo.editor.mark_saved(Path("x"))
    assert demo.open_project(path)
    assert demo.current_run_id == "R1"
    assert demo.plate.selected_coords() == []
    assert demo.selection.sample_edit.text() == ""


def test_old_results_do_not_outlive_a_failed_analysis(demo, tmp_path, monkeypatch):
    from qpcr_core.sessions import save_project
    import ui.main_window as mw

    path = tmp_path / "other.qpcrkit.json"
    save_project(make_project([("R1", "A1", "s", "T", "unknown", 20.0, None)]), path)
    demo.editor.mark_saved(Path("x"))

    def fail(project):
        raise RuntimeError("odd data")

    monkeypatch.setattr(mw, "analyze", fail)
    assert demo.open_project(path)
    assert demo.results is None


def test_undo_of_a_run_clears_its_selection(demo):
    demo.add_run(RUN1)
    new = demo.current_run_id
    demo.plate.select_coords(["A1"])
    demo.editor.undo()
    assert demo.current_run_id != new
    assert demo.plate.selected_coords() == []


def test_saving_a_figure_waits_for_the_recalculation(demo, tmp_path, monkeypatch):
    from qpcr_core.editing import update_settings

    demo.editor.apply(update_settings, control_group="LPS")
    assert demo._timer.isActive()
    calls = []
    real = demo.recalculate_now
    monkeypatch.setattr(demo, "recalculate_now", lambda: (calls.append(1), real()))
    monkeypatch.setattr(demo, "_ask_save_path", lambda *a: str(tmp_path / "f.svg"))
    demo._save_expression_figure("IL6")
    assert calls and (tmp_path / "f.svg").exists()


def test_saving_without_results_does_nothing(demo, tmp_path, monkeypatch):
    import ui.main_window as mw

    demo.results = None

    def fail(project):
        raise RuntimeError("odd data")

    monkeypatch.setattr(mw, "analyze", fail)
    monkeypatch.setattr(demo, "_ask_save_path", lambda *a: str(tmp_path / "f.svg"))
    demo._save_expression_figure("IL6")
    assert not (tmp_path / "f.svg").exists()


# --- the rebuild and closing ---


def test_open_settings_dialog_stays_open_over_a_language_switch(demo):
    demo.top_bar.settings_requested.emit()
    demo.set_language("en")
    assert demo.analysis.isVisible()
    demo.analysis.close()
    demo.set_language("ru")
    assert not demo.analysis.isVisible()


def test_color_mode_survives_a_language_switch(demo):
    demo.color_combo.setCurrentIndex(demo.color_combo.findData("role"))
    demo.set_language("en")
    assert demo.plate.color_mode == "role" and demo.color_combo.currentData() == "role"
    demo.set_language("ru")


def test_closing_the_window_closes_the_dialog_and_the_timer(demo):
    demo.top_bar.settings_requested.emit()
    demo.editor.apply(set_target_kind, "IL6", "target")
    demo.editor.mark_saved(Path("x"))
    demo.close()
    assert not demo.analysis.isVisible() and not demo._timer.isActive()


def test_margins_drop_the_saved_picture(view):  # noqa: F811
    view.canvas.draw()
    assert view._background is not None
    view.figure.set_size_inches(4.0, 3.0)  # a new size: the saved picture no longer fits
    view._fit_margins()
    assert view._background is None and view._segments_px is None


@pytest.mark.parametrize("bad", ["nan", "inf", "-1", "0"])
def test_table_refuses_a_bad_quantity(qapp, bad):
    from PySide6.QtCore import Qt

    from ui.data_table import COLUMNS, ReactionModel

    p = make_project([("R1", "A1", "s", "T", "std", 20.0, 100.0)])
    m = ReactionModel(ProjectEditor(p))
    assert not m.setData(m.index(0, COLUMNS.index("quantity")), bad, Qt.ItemDataRole.EditRole)
    assert p.runs[0].wells["A1"].reactions[0].quantity == 100.0


# --- the check before the release ---


def _sybr_plate(win):
    wells = {f"A{i}": Well(f"A{i}", "s", [Reaction(target="SYBR", fluor="SYBR", cq=20.0)]) for i in range(1, 4)}
    p = Project(runs=[Run(id="R1", name="R1", wells=wells, thresholds={"SYBR": 0.2})])
    p.ensure_targets_and_samples()
    win.editor.set_project(p)
    return p


def test_rename_a_target_on_the_plate(win):
    _sybr_plate(win)
    assert win.hint_bar.label.text() == tr("hint.no_target", count=3)
    win.rename_target("SYBR", "GAPDH")
    run = win.editor.project.runs[0]
    assert {r.target for w in run.wells.values() for r in w.reactions} == {"GAPDH"}
    assert run.thresholds == {"GAPDH": 0.2}
    assert list(win.editor.project.targets) == ["GAPDH"]
    win.editor.undo()
    assert list(win.editor.project.targets) == ["SYBR"]


def test_rename_from_the_edit_menu(win, monkeypatch):
    _sybr_plate(win)
    monkeypatch.setattr(win, "_ask_rename", lambda names: ("SYBR", "GAPDH") if names == ["SYBR"] else None)
    action = next(a for m in win.menuBar().actions() for a in m.menu().actions() if a.text() == tr("act.rename_target"))
    action.trigger()
    assert list(win.editor.project.targets) == ["GAPDH"]


def test_rename_cancelled_or_without_a_run(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "_ask_rename", lambda names: calls.append(names))
    win._rename_target_dialog()  # no run yet: nothing to ask
    assert calls == []
    _sybr_plate(win)
    win.editor.mark_saved(Path("x"))
    win._rename_target_dialog()
    assert calls == [["SYBR"]] and not win.editor.dirty


def test_licenses_of_the_icons_are_bundled():
    spec = (Path(__file__).resolve().parent.parent / "qpcrkit.spec").read_text(encoding="utf-8")
    assert '"ui/icons/LICENSE"' in spec


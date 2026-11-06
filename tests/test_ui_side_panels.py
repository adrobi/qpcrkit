from i18n import tr
from tests.test_pipeline import demo_project
from ui.editor import ProjectEditor
from ui.side_panels import ProjectTree, SettingsPanel


def _panel():
    p = demo_project()
    p.targets["GAPDH"].kind = "target"
    p.settings.control_group = ""
    e = ProjectEditor(p)
    return e, SettingsPanel(e)


def test_threshold_and_test(qapp):
    e, s = _panel()
    s.spins["rep_sd_max"].setValue(0.5)
    assert e.project.settings.rep_sd_max == 0.5
    s.test_combo.setCurrentIndex(s.test_combo.findData("tukey"))
    assert e.project.settings.test == "tukey"
    s.pool_check.setChecked(False)
    assert e.project.settings.pool_std_runs is False


def test_efficiency_mode(qapp):
    e, s = _panel()
    s.eff_mode["IL6"].setCurrentIndex(s.eff_mode["IL6"].findData("manual"))
    s.eff_value["IL6"].setValue(0.95)
    t = e.project.targets["IL6"]
    assert (t.efficiency_mode, t.efficiency_manual) == ("manual", 0.95)


def test_refresh_after_undo_keeps_widgets_in_sync(qapp):
    e, s = _panel()
    s.eff_mode["IL6"].setCurrentIndex(s.eff_mode["IL6"].findData("ideal"))
    e.undo()
    assert s.eff_mode["IL6"].currentData() == "stdcurve"


def test_project_tree(qapp):
    t = ProjectTree()
    t.refresh(demo_project())
    hits = []
    t.run_selected.connect(hits.append)
    t.tree.itemClicked.emit(t.run_item("R2"), 0)
    assert hits == ["R2"]
    asked = []
    t.add_run_requested.connect(lambda: asked.append(1))
    t.add_run_button.click()
    assert asked == [1]


# --- the analysis dialog ---


def _with_curves():
    from qpcr_core.pipeline import analyze
    from tests.curve_factory import logistic
    from tests.test_curve_pipeline import _project

    p = _project(
        [("R1", f"A{i + 1}", f"s{i}", "T", "unknown", 20.0 + i, logistic(18 + i, seed=i, noise=0.002)) for i in range(10)]
        + [("R1", "B1", "x", "U", "unknown", 22.0, None)]
    )
    e = ProjectEditor(p)
    s = SettingsPanel(e)
    s.set_results(analyze(p))
    return e, s


def test_cq_source(qapp):
    e, s = _with_curves()
    assert s.cq_source_combo.currentData() == "instrument"
    s.cq_source_combo.setCurrentIndex(s.cq_source_combo.findData("calculated"))
    assert e.project.settings.cq_source == "calculated"
    e.undo()
    assert e.project.settings.cq_source == "instrument"
    assert s.cq_source_combo.currentData() == "instrument"


def test_new_thresholds_reach_the_settings(qapp):
    e, s = _with_curves()
    for name, value in (("nrt_min_delta", 4.0), ("tm_shift_max", 0.7), ("early_cq", 12.0), ("cq_disagree_max", 0.9)):
        s.spins[name].setValue(value)
        assert getattr(e.project.settings, name) == value


def test_curves_mode(qapp):
    from qpcr_core.pipeline import analyze

    e, s = _with_curves()
    combo = s.eff_mode["T"]
    combo.setCurrentIndex(combo.findData("curves"))
    assert e.project.targets["T"].efficiency_mode == "curves"
    assert analyze(e.project).efficiency_source["T"] == "curves"


def _item_enabled(combo, data) -> bool:
    return combo.model().item(combo.findData(data)).isEnabled()


def test_curves_mode_needs_curves(qapp):
    _, s = _with_curves()
    assert _item_enabled(s.eff_mode["T"], "curves")
    assert not _item_enabled(s.eff_mode["U"], "curves")


def test_curves_mode_already_chosen_stays_available(qapp):
    from qpcr_core.pipeline import analyze

    e, s = _with_curves()
    e.apply(lambda p: setattr(p.targets["U"], "efficiency_mode", "curves"))
    s.set_results(analyze(e.project))
    assert _item_enabled(s.eff_mode["U"], "curves")
    assert s.eff_mode["U"].currentData() == "curves"


def test_curve_efficiency_is_shown(qapp):
    _, s = _with_curves()
    assert "9" in s.curve_eff_label["T"].text()  # about 95 %
    assert s.curve_eff_label["U"].text() == ""


def test_shown_efficiency_survives_a_rebuild_of_the_rows(qapp):
    from qpcr_core.editing import rename_target_in_run

    e, s = _with_curves()
    e.apply(rename_target_in_run, "R1", "U", "V")
    assert "9" in s.curve_eff_label["T"].text()
    assert _item_enabled(s.eff_mode["T"], "curves")


def test_panel_without_results(qapp):
    p = demo_project()
    e = ProjectEditor(p)
    s = SettingsPanel(e)
    assert not _item_enabled(s.eff_mode["IL6"], "curves")
    assert s.curve_eff_label["IL6"].text() == ""


def test_window_passes_results_to_the_dialog(win):
    from tests.test_curve_pipeline import _project
    from tests.curve_factory import logistic

    win.editor.set_project(
        _project([("R1", f"A{i + 1}", f"s{i}", "T", "unknown", 20.0, logistic(18 + i, seed=i, noise=0.002)) for i in range(10)])
    )
    win.recalculate_now()
    panel = win.analysis.panel
    assert "9" in panel.curve_eff_label["T"].text()
    win.set_language("en")
    assert "9" in win.analysis.panel.curve_eff_label["T"].text()


def test_dialog_source_changes_the_results(win):
    from tests.test_curve_pipeline import _project
    from tests.curve_factory import logistic

    win.editor.set_project(
        _project([("R1", f"A{i + 1}", f"s{i}", "T", "unknown", 40.0, logistic(18 + i, seed=i, noise=0.002)) for i in range(4)])
    )
    win.recalculate_now()
    assert win.results.mean_cq[("s0", "T")] == 40.0
    combo = win.analysis.panel.cq_source_combo
    combo.setCurrentIndex(combo.findData("calculated"))
    win.recalculate_now()
    assert win.results.mean_cq[("s0", "T")] < 30


def test_menu_opens_the_dialog(win):
    action = next(a for m in win.menuBar().actions() for a in m.menu().actions() if a.text() == tr("ui.analysis_settings"))
    action.trigger()
    assert win.analysis.isVisible()
    win.analysis.close()

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

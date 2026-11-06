"""The panel under the plate: what the selected wells hold, and editing them."""

from __future__ import annotations

from i18n import tr
from qpcr_core.models import Project, Reaction, Run, Sample, Well
from ui.selection_panel import SelectionPanel


def _setup():
    wells = {
        "A1": Well("A1", "s1", [Reaction(target="T", cq=20.0, quantity=100.0)]),
        "A2": Well("A2", "s1", [Reaction(target="T", cq=21.0, quantity=100.0)]),
        "A3": Well("A3", "s2", [Reaction(target="U", cq=22.0)]),
    }
    run = Run(id="R", name="R", wells=wells)
    p = Project(runs=[run], samples={"s1": Sample("s1", group="Ctrl"), "s2": Sample("s2", group="LPS")})
    p.ensure_targets_and_samples()
    return p, run


def test_disabled_without_selection(qapp):
    panel = SelectionPanel()
    p, run = _setup()
    panel.set_selection(p, run, [])
    for w in (panel.target_edit, panel.sample_edit, panel.group_edit, panel.role_combo, panel.quantity_edit, panel.apply_button):
        assert not w.isEnabled()
    assert panel.label.text() == tr("ui.select_wells")


def test_one_value_is_shown_as_a_placeholder(qapp):
    panel = SelectionPanel()
    p, run = _setup()
    panel.set_selection(p, run, ["A1", "A2"])
    assert panel.target_edit.isEnabled()
    assert panel.target_edit.placeholderText() == "T"
    assert panel.sample_edit.placeholderText() == "s1"
    assert panel.group_edit.placeholderText() == "Ctrl"
    assert panel.quantity_edit.placeholderText() == "100"
    assert panel.target_edit.text() == ""  # a placeholder, so Apply does not rewrite it
    assert "2" in panel.label.text()


def test_different_values_say_so(qapp):
    panel = SelectionPanel()
    p, run = _setup()
    panel.set_selection(p, run, ["A1", "A3"])
    assert panel.target_edit.placeholderText() == tr("ui.mixed")
    assert panel.sample_edit.placeholderText() == tr("ui.mixed")
    assert panel.group_edit.placeholderText() == tr("ui.mixed")


def test_empty_values_show_the_field_name(qapp):
    panel = SelectionPanel()
    p = Project(runs=[Run(id="R", name="R", wells={"A1": Well("A1", None, [Reaction(target="T")])})])
    panel.set_selection(p, p.runs[0], ["A1"])
    assert panel.sample_edit.placeholderText() == tr("ui.col.sample")
    assert panel.group_edit.placeholderText() == tr("ui.col.group")


def test_typed_text_survives_a_new_selection(qapp):
    panel = SelectionPanel()
    p, run = _setup()
    panel.set_selection(p, run, ["A1"])
    panel.sample_edit.setText("new")
    panel.set_selection(p, run, ["A2"])
    assert panel.sample_edit.text() == "new"
    panel.clear_fields()
    assert panel.sample_edit.text() == "" and panel.role_combo.currentData() is None


def test_signals(qapp):
    panel = SelectionPanel()
    p, run = _setup()
    panel.set_selection(p, run, ["A1"])
    got = []
    panel.apply_requested.connect(lambda: got.append("apply"))
    panel.series_requested.connect(lambda: got.append("series"))
    panel.exclude_requested.connect(got.append)
    panel.apply_button.click()
    panel.series_button.click()
    panel.exclude_button.click()
    panel.include_button.click()
    assert got == ["apply", "series", True, False]


def test_enter_applies(qapp):
    panel = SelectionPanel()
    p, run = _setup()
    panel.set_selection(p, run, ["A1"])
    got = []
    panel.apply_requested.connect(lambda: got.append(1))
    panel.sample_edit.returnPressed.emit()
    assert got == [1]


def test_window_fills_and_clears_the_panel(demo):
    demo.select_run("R1")
    coord = next(c for c, w in demo.editor.project.run("R1").wells.items() if w.sample)
    demo.plate.select_coords([coord])
    assert demo.selection.sample_edit.placeholderText() == demo.editor.project.run("R1").wells[coord].sample
    demo.selection.sample_edit.setText("Renamed")
    demo.selection.apply_button.click()
    assert demo.editor.project.run("R1").wells[coord].sample == "Renamed"
    assert demo.selection.sample_edit.text() == ""
    assert demo.plate.selected_coords() == [coord]
    assert demo.selection.sample_edit.placeholderText() == "Renamed"

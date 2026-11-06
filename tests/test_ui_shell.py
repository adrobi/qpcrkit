"""The window frame: navigation, top bar, hint line."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QEvent

from qpcr_core.editing import set_group, set_target_kind
from qpcr_core.hints import Hint
from tests.test_pipeline import demo_project
from ui.editor import ProjectEditor
from ui.main_window import PAGE_NAMES
from ui.shell import HintBar, NavRail, TopBar


def _bar(project=None):
    p = project or demo_project()
    e = ProjectEditor(p)
    bar = TopBar(e)
    bar.refresh(p, None)
    return e, bar


def _action(menu, text):
    return next(a for a in menu.actions() if a.text() == text)


# --- navigation ---


def test_nav_buttons_select_pages(qapp):
    nav = NavRail()
    got = []
    nav.page_selected.connect(got.append)
    nav.buttons["expr"].click()
    assert got == ["expr"] and nav.buttons["expr"].isChecked()
    nav.set_page("qc")
    assert nav.buttons["qc"].isChecked() and not nav.buttons["expr"].isChecked()
    assert got == ["expr"]  # setting the page from code is not a request


def test_qc_counter(qapp):
    nav = NavRail()
    plain = nav.buttons["qc"].text()
    nav.set_qc_count(2, 3)
    assert "5" in nav.buttons["qc"].text()
    assert "2" in nav.buttons["qc"].toolTip() and "3" in nav.buttons["qc"].toolTip()
    nav.set_qc_count(0, 0)
    assert nav.buttons["qc"].text() == plain


def test_window_pages(demo):
    assert PAGE_NAMES == ("plate", "data", "std", "expr", "qc")
    for name in PAGE_NAMES:
        demo.go_to(name)
        assert demo.current_page() == name
        assert demo.nav.buttons[name].isChecked()
    demo.nav.buttons["data"].click()
    assert demo.pages.currentWidget() is demo.data


def test_runs_are_listed_in_navigation(demo):
    assert demo.nav.tree.run_item("R2") is not None
    demo.nav.tree.tree.itemClicked.emit(demo.nav.tree.run_item("R2"), 0)
    assert demo.current_run_id == "R2"


def test_qc_counter_follows_the_results(demo):
    plain = demo.nav.buttons["qc"].text()
    demo.editor.apply(set_target_kind, "GAPDH", "target")  # no reference: an error
    demo.recalculate_now()
    r = demo.results
    n = len(r.flags_by_severity("error")) + len(r.flags_by_severity("warning"))
    assert n > 0 and str(n) in demo.nav.buttons["qc"].text()
    demo.editor.undo()
    demo.recalculate_now()
    assert demo.nav.buttons["qc"].text() == plain


def test_locate_goes_to_the_plate(demo):
    demo.go_to("qc")
    demo.qc.locate.emit("R2", "A3")
    assert demo.current_page() == "plate"
    assert demo.current_run_id == "R2" and demo.plate.selected_coords() == ["A3"]


# --- chips ---


def test_reference_chip(qapp):
    e, bar = _bar()
    assert bar.ref_chip.property("missing") is False  # the demo has a reference
    e.apply(set_target_kind, "GAPDH", "target")
    bar.refresh(e.project, None)
    assert bar.ref_chip.property("missing") is True
    _action(bar.ref_chip.menu(), "GAPDH").trigger()
    assert e.project.targets["GAPDH"].kind == "reference"
    bar.refresh(e.project, None)
    assert bar.ref_chip.property("missing") is False and "GAPDH" in bar.ref_chip.text()
    e.undo()
    assert e.project.targets["GAPDH"].kind == "target"


def test_reference_chip_unchecks(qapp):
    e, bar = _bar()
    action = _action(bar.ref_chip.menu(), "GAPDH")
    assert action.isChecked()
    action.trigger()
    assert e.project.targets["GAPDH"].kind == "target"


def test_control_chip(qapp):
    p = demo_project()
    p.settings.control_group = ""
    e, bar = _bar(p)
    assert bar.control_chip.property("missing") is True
    _action(bar.control_chip.menu(), "LPS").trigger()
    assert e.project.settings.control_group == "LPS"
    bar.refresh(e.project, None)
    assert bar.control_chip.property("missing") is False and "LPS" in bar.control_chip.text()
    assert _action(bar.control_chip.menu(), "LPS").isChecked()


def test_calibrator_counts_as_a_control(qapp):
    p = demo_project()
    p.settings.control_group = ""
    p.settings.calibrator_sample = "c1"
    _, bar = _bar(p)
    assert bar.control_chip.property("missing") is False and "c1" in bar.control_chip.text()


def test_control_chip_without_groups_says_so(qapp):
    p = demo_project()
    p.settings.control_group = ""
    for s in p.samples.values():
        s.group = ""
    _, bar = _bar(p)
    actions = bar.control_chip.menu().actions()
    assert len(actions) == 1 and not actions[0].isEnabled()


def test_project_name_and_settings_button(qapp, tmp_path):
    e, bar = _bar()
    bar.refresh(e.project, tmp_path / "exp.qpcrkit.json")
    assert "exp.qpcrkit.json" in bar.name_label.text()
    got = []
    bar.settings_requested.connect(lambda: got.append(1))
    bar.settings_button.click()
    assert got == [1]


# --- the hint line ---


def test_hint_bar(qapp):
    h = HintBar()
    h.set_hint(Hint("hint.no_target", {"count": 12}))
    assert "12" in h.label.text() and not h.isHidden()
    h.set_hint(None)
    assert h.isHidden()


def test_hint_follows_the_project(demo):
    assert demo.hint_bar.isHidden()
    demo.editor.apply(set_target_kind, "GAPDH", "target")
    assert not demo.hint_bar.isHidden()


# --- the frame survives a rebuild ---


def test_language_switch_keeps_page_run_and_selection(demo):
    demo.go_to("plate")
    demo.select_run("R2")
    demo.plate.select_coords(["A1", "A2"])
    demo.set_language("en")
    assert demo.current_page() == "plate" and demo.current_run_id == "R2"
    assert demo.plate.selected_coords() == ["A1", "A2"]
    demo.go_to("expr")
    demo.set_language("ru")
    assert demo.current_page() == "expr" and demo.nav.buttons["expr"].isChecked()


def test_theme_switch_keeps_page_and_selection(demo):
    demo.go_to("plate")
    demo.plate.select_coords(["A1"])
    demo.apply_theme("dark", save=False)
    demo.apply_theme("light", save=False)
    assert demo.current_page() == "plate" and demo.plate.selected_coords() == ["A1"]


def test_settings_dialog_opens_and_survives_a_language_switch(demo):
    demo.top_bar.settings_requested.emit()
    assert demo.analysis.isVisible()
    old = demo.analysis
    demo.set_language("en")
    assert demo.analysis is not old
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    demo.editor.apply(set_group, "Ctrl-1", "Ctrl")  # must not reach the deleted panel

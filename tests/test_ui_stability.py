"""The stability page."""

from __future__ import annotations

import pytest

from i18n import tr
from qpcr_core.editing import set_references
from qpcr_core.pipeline import analyze
from tests.test_pipeline import demo_project
from tests.test_stability import _three_refs
from ui.editor import ProjectEditor
from ui.stability_tab import StabilityTab


def _tab(project):
    editor = ProjectEditor(project)
    tab = StabilityTab(editor)
    tab.resize(1000, 700)
    tab.set_results(project, analyze(project), False)
    editor.changed.connect(lambda: tab.set_results(editor.project, analyze(editor.project), False))
    return editor, tab


def test_set_references_only_among_the_given_targets():
    p = _three_refs(refs=("R1", "R2", "R3"))
    p.targets["T"].kind = "target"
    set_references(p, ["R1", "T"], among=["R1", "R2", "T"])
    kinds = {n: t.kind for n, t in p.targets.items()}
    assert kinds == {"R1": "reference", "R2": "target", "R3": "reference", "T": "reference"}


def test_candidates_are_listed_with_their_samples(qapp):
    _, tab = _tab(_three_refs())
    assert set(tab.candidate_checks) == {"R1", "R2", "R3", "T"}
    assert tab.candidate_checks["R1"].isChecked() and not tab.candidate_checks["T"].isChecked()
    assert "8" in tab.candidate_checks["R1"].text()


def test_a_check_box_changes_the_candidates_and_can_be_undone(qapp):
    editor, tab = _tab(_three_refs())
    tab.candidate_checks["T"].setChecked(True)
    assert editor.project.targets["T"].stability_candidate is True
    assert tab.candidate_checks["T"].isChecked()
    editor.undo()
    assert editor.project.targets["T"].stability_candidate is None
    assert not tab.candidate_checks["T"].isChecked()


def _four():
    return _three_refs(shift_lps=3.0, refs=("R1", "R2", "R3", "R4"), fourth=True)


def test_summary_and_figures(qapp):
    p = _four()
    _, tab = _tab(p)
    advice = analyze(p).stability.recommended
    assert "R3" not in advice and all(g in tab.summary.text() for g in advice)
    assert tab.genorm_canvas.mpl_canvas is not None and tab.normfinder_canvas.mpl_canvas is not None
    assert tab.normfinder_table.rowCount() == 4
    assert tab.need_more.isHidden()


def test_the_button_makes_the_advice_the_references(qapp):
    p = _four()
    editor, tab = _tab(p)
    advice = set(analyze(p).stability.recommended)
    assert tab.apply_button.isEnabled()
    tab.apply_button.click()
    refs = {n for n, t in editor.project.targets.items() if t.kind == "reference"}
    assert refs == advice
    assert not tab.apply_button.isEnabled()
    editor.undo()
    assert {n for n, t in editor.project.targets.items() if t.kind == "reference"} == {"R1", "R2", "R3", "R4"}


def test_button_off_when_the_advice_is_already_followed(qapp):
    _, tab = _tab(_three_refs(refs=("R1", "R2")))  # two candidates: the advice is both, they are references
    assert not tab.apply_button.isEnabled()


def test_a_reference_outside_the_candidates_does_not_keep_the_button_on(qapp):
    p = _four()
    p.targets["T"].kind = "reference"
    p.targets["T"].stability_candidate = False
    editor, tab = _tab(p)
    tab.apply_button.click()
    assert editor.project.targets["T"].kind == "reference"
    assert not tab.apply_button.isEnabled()


def test_too_little_data_is_explained(qapp):
    _, tab = _tab(demo_project())  # one reference
    assert not tab.need_more.isHidden()
    assert tr("stab.note.few_candidates") in tab.need_more.text()
    assert tab.genorm_canvas.isHidden() and tab.normfinder_canvas.isHidden()
    assert not tab.apply_button.isEnabled()


def test_without_groups_normfinder_says_so(qapp):
    p = _three_refs()
    for s in p.samples.values():
        s.group = ""
    _, tab = _tab(p)
    assert tr("stab.note.no_groups") in tab.notes.text()


def test_page_in_the_window(win):
    from ui.main_window import PAGE_NAMES

    assert PAGE_NAMES.index("stab") == PAGE_NAMES.index("std") + 1
    win.editor.set_project(_three_refs(shift_lps=3.0))
    win.recalculate_now()
    win.go_to("stab")
    assert win.pages.currentWidget() is win.stab
    assert win.stab.normfinder_table.rowCount() == 3
    win.apply_theme("dark", save=False)
    win.set_language("en")
    assert win.current_page() == "stab" and win.stab.normfinder_table.rowCount() == 3
    win.set_language("ru")
    win.apply_theme("light", save=False)


def test_m_limit_in_the_settings(win):
    win.editor.set_project(_three_refs(shift_lps=1.0))
    win.recalculate_now()
    m = win.results.stability.genorm_m["R3"]
    spin = win.analysis.panel.spins["genorm_m_max"]
    assert spin.toolTip()
    spin.setValue(round(m + 0.2, 2))
    win.recalculate_now()
    assert not [f for f in win.results.flags if f.code == "reference_unstable"]
    spin.setValue(round(max(m - 0.2, 0.1), 2))
    win.recalculate_now()
    assert [f for f in win.results.flags if f.code == "reference_unstable"]

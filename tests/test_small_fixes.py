"""Small fixes of 1.2: legend names, duplicate reactions, a failed analysis."""

from __future__ import annotations

import pytest

from i18n import tr
from qpcr_core.models import Project, Reaction, Run, Well
from qpcr_core.pipeline import analyze
from tests.curve_factory import logistic
from tests.test_curve_pipeline import _project


# --- 1. a name with a leading underscore ---


def test_underscore_name_stays_in_the_legend():
    from qpcr_core.figures import amplification_figure

    rows = [("R1", "A1", "s", "_ACTB", "unknown", None, logistic(22)), ("R1", "A2", "s", "IL6", "unknown", None, logistic(25))]
    p = _project(rows)
    ax = amplification_figure(p, analyze(p), "R1").axes[0]
    labels = [t.get_text() for t in ax.get_legend().get_texts()]
    assert any(label.endswith("_ACTB") for label in labels) and len(labels) == 2


# --- 2. two reactions of one well with the same target and dye ---


def _duplicated(with_curves: bool):
    first = Reaction(target="T", fluor="FAM", cq=20.0, amplification=logistic(20) if with_curves else None)
    second = Reaction(target="T", fluor="FAM", cq=30.0, amplification=logistic(30) if with_curves else None)
    wells = {"A1": Well("A1", "s1", [first, second]), "A2": Well("A2", "s1", [Reaction(target="T", fluor="FAM", cq=20.2)])}
    p = Project(runs=[Run(id="R1", name="R1", wells=wells)])
    p.ensure_targets_and_samples()
    return p


@pytest.mark.parametrize("with_curves", [False, True])
def test_duplicate_reaction_is_flagged_and_left_out(with_curves):
    res = analyze(_duplicated(with_curves))
    flag = next(f for f in res.flags if f.code == "duplicate_reaction")
    assert flag.severity == "warning" and flag.coords == ("A1",) and flag.run_id == "R1"
    assert res.mean_cq[("s1", "T")] == pytest.approx(20.1)  # the second reaction of A1 is not counted
    assert not [f for f in res.flags if f.code in ("rep_sd_high", "partial_undetermined")]


def test_duplicate_curve_result_is_the_first():
    res = analyze(_duplicated(True))
    assert res.curves[("R1", "A1", "T", "FAM")].cq_calc < 25


def test_an_excluded_duplicate_is_no_duplicate():
    p = _duplicated(False)
    p.runs[0].wells["A1"].reactions[1].excluded = True
    assert not [f for f in analyze(p).flags if f.code == "duplicate_reaction"]


def test_flag_has_a_text():
    assert tr("qc.duplicate_reaction") != "qc.duplicate_reaction"


# --- 3. a failed analysis ---


def test_failed_analysis_clears_the_pages_and_success_brings_them_back(demo, monkeypatch):
    import ui.main_window as mw

    real = mw.analyze

    def fail(project):
        raise RuntimeError("odd data")

    monkeypatch.setattr(mw, "analyze", fail)
    demo.recalculate_now()
    message = tr("ui.analysis_failed", error="odd data")
    assert demo.results is None
    for page in (demo.std, demo.expr, demo.qc, demo.stab):
        assert page.failure.text() == message and not page.failure.isHidden()
    assert demo.std.curve_count() == 0 and demo.qc.tree.topLevelItemCount() == 0
    assert not demo.expr.save_button.isEnabled()
    assert demo.curves.line_count() == 0 or demo.curves.results is None
    assert demo.nav.buttons["qc"].text() == tr("tab.qc")

    monkeypatch.setattr(mw, "analyze", real)
    demo.recalculate_now()
    for page in (demo.std, demo.expr, demo.qc, demo.stab):
        assert page.failure.isHidden()
    assert demo.std.curve_count() == 1 and demo.expr.save_button.isEnabled()


# --- 4. the first selection ---


def _drawn_view(qapp):
    from tests.test_ui_curve_view import _rows
    from ui.curve_view import CurveView

    p = _project(_rows())
    v = CurveView()
    v.resize(700, 500)
    v.set_data(p, analyze(p), "R1")
    v.canvas.draw()  # the first full draw, as on screen
    return v


def test_first_selection_needs_no_full_draw(qapp):
    v = _drawn_view(qapp)
    draws = []
    v.canvas.mpl_connect("draw_event", lambda e: draws.append(1))
    v.set_selection(["A1"])
    v.set_selection(["A1", "A2"])
    assert draws == []
    v.deleteLater()


def test_same_size_keeps_the_saved_picture(qapp):
    v = _drawn_view(qapp)
    saved = v._background
    v._fit_margins()
    assert v._background is saved
    v.figure.set_size_inches(3.0, 3.0)
    v._fit_margins()
    assert v._background is None
    v.deleteLater()

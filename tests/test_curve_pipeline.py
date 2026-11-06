"""Curves inside analyze(): source of Cq, thresholds, efficiency from curves."""

from __future__ import annotations

from pathlib import Path

import pytest

from qpcr_core import curves as cv
from qpcr_core.importers.detect import import_file
from qpcr_core.models import Curve, Project, Reaction, Run, Settings, Target, Well
from qpcr_core.pipeline import analyze
from tests.curve_factory import flat, logistic, melt

REAL = Path(__file__).parent / "data" / "real"


def _project(rows, **settings) -> Project:
    """rows: run, coord, sample, target, role, cq, curve; or the same with a ninth item, the melt."""
    p = Project(settings=Settings(**settings))
    runs: dict[str, Run] = {}
    for run_id, coord, sample, target, role, cq, curve, *rest in rows:
        run = runs.get(run_id)
        if run is None:
            run = runs[run_id] = Run(id=run_id, name=run_id)
            p.runs.append(run)
        well = run.wells.setdefault(coord, Well(coord, sample))
        well.reactions.append(
            Reaction(target=target, fluor="FAM", role=role, cq=cq, amplification=curve, melt=rest[0] if rest else None)
        )
    p.ensure_targets_and_samples()
    return p


def _codes(results) -> list[str]:
    return [f.code for f in results.flags]


def _key(run, coord, target="T"):
    return (run, coord, target, "FAM")


def _plate(run="R1", cqs=(20, 22, 24, 26), instrument_cq=None, **kw):
    return [
        (run, f"A{i + 1}", f"s{i}", "T", "unknown", instrument_cq, logistic(c, seed=i, noise=0.002, **kw))
        for i, c in enumerate(cqs)
    ]


# --- results per reaction ---


def test_results_per_reaction():
    res = analyze(_project(_plate()))
    r = res.curves[_key("R1", "A2")]
    assert r.threshold > 0
    assert r.cq_calc - res.curves[_key("R1", "A1")].cq_calc == pytest.approx(2.0, abs=0.15)
    assert r.efficiency == pytest.approx(0.95, abs=0.1)
    assert r.window_r2 > 0.9
    assert r.tms == ()
    assert r.baseline_subtracted is False


def test_broken_curve_gives_no_cq_and_a_flag_not_an_exception():
    rows = _plate()
    rows.append(("R1", "B1", "s9", "T", "unknown", None, Curve([1, 2, 3], [1.0, 2.0, 3.0])))
    res = analyze(_project(rows))
    assert res.curves[_key("R1", "B1")].cq_calc is None
    assert "curve_unusable" in _codes(res)
    assert res.curves[_key("R1", "A1")].cq_calc is not None


def test_reaction_without_curves_has_no_result():
    p = _project([("R1", "A1", "s", "T", "unknown", 25.0, None)])
    assert analyze(p).curves == {}


# --- the source of Cq ---


def _undetermined(**settings) -> Project:
    rows = _plate(instrument_cq=None)
    rows = [(*r[:5], 20.0 + i, r[6]) for i, r in enumerate(rows)]
    rows[1] = (*rows[1][:5], None, rows[1][6])  # the instrument says Undetermined, the curve grows
    return _project(rows, **settings)


def test_instrument_source_keeps_undetermined():
    res = analyze(_undetermined())
    assert res.mean_cq[("s1", "T")] is None
    assert res.mean_cq[("s0", "T")] == 20.0


def test_calculated_source_uses_our_cq():
    res = analyze(_undetermined(cq_source="calculated"))
    assert res.mean_cq[("s1", "T")] == pytest.approx(res.curves[_key("R1", "A2")].cq_calc)
    assert res.mean_cq[("s0", "T")] == pytest.approx(res.curves[_key("R1", "A1")].cq_calc)


def test_run_without_instrument_cq_uses_ours_by_default():
    res = analyze(_project(_plate()))
    assert res.mean_cq[("s0", "T")] == pytest.approx(res.curves[_key("R1", "A1")].cq_calc)


def test_excluded_reaction_has_no_cq_in_either_source():
    p = _project(_plate(), cq_source="calculated")
    p.runs[0].wells["A1"].reactions[0].excluded = True
    assert analyze(p).mean_cq.get(("s0", "T")) is None


def test_run_uses_calculated():
    run = Run(id="R", name="R", wells={"A1": Well("A1", "s", [Reaction(target="T", cq=20.0)])})
    assert cv.run_uses_calculated(run, Settings()) is False
    assert cv.run_uses_calculated(run, Settings(cq_source="calculated")) is True
    run.wells["A1"].reactions[0].cq = None
    assert cv.run_uses_calculated(run, Settings()) is True


def _mixed(irc: bool) -> Project:
    rows = [(*r[:5], 20.0 + i, r[6]) for i, r in enumerate(_plate("R1"))] + _plate("R2")
    if irc:
        curve = logistic(25)
        rows += [("R1", "H1", "cal", "T", "irc", 25.0, curve), ("R2", "H1", "cal", "T", "irc", None, curve)]
    return _project(rows)


def test_mixed_sources_without_irc_is_an_error():
    flag = next(f for f in analyze(_mixed(False)).flags if f.code == "mixed_cq_sources")
    assert flag.severity == "error" and flag.target == "T"


def test_mixed_sources_with_irc_is_a_warning():
    flag = next(f for f in analyze(_mixed(True)).flags if f.code == "mixed_cq_sources")
    assert flag.severity == "warning"


def test_one_source_is_not_mixed():
    assert "mixed_cq_sources" not in _codes(analyze(_project(_plate("R1") + _plate("R2"))))


def test_reactions_without_curves_when_calculated():
    rows = _plate()
    rows.append(("R1", "B1", "x", "T", "unknown", 21.0, None))
    res = analyze(_project(rows, cq_source="calculated"))
    flag = next(f for f in res.flags if f.code == "no_curve_for_calculated")
    assert flag.severity == "warning" and flag.run_id == "R1" and flag.coords == ("B1",)
    assert res.mean_cq[("x", "T")] is None
    assert res.mean_cq[("s0", "T")] is not None


def test_instrument_source_does_not_ask_for_curves():
    p = _project([("R1", "A1", "s", "T", "unknown", 25.0, None)])
    assert "no_curve_for_calculated" not in _codes(analyze(p))


def test_qc_sees_our_cq():
    rows = _plate()
    rows.append(("R1", "H1", None, "T", "ntc", None, logistic(15)))
    res = analyze(_project(rows, cq_source="calculated"))
    assert "ntc_contamination" in _codes(res)
    assert "ntc_contamination" not in _codes(analyze(_project(_only_cq(rows))))


def _only_cq(rows):
    """The same plate on the instrument's word: every sample has a Cq, the NTC has none."""
    return [(*r[:5], 22.0 if r[4] != "ntc" else None, r[6]) for r in rows]


def test_calibration_sees_our_cq():
    rows = _plate("R1") + _plate("R2")
    rows += [("R1", "H1", "cal", "T", "irc", 25.0, logistic(25)), ("R2", "H1", "cal", "T", "irc", 25.0, logistic(27))]
    rows += [("R1", "H2", "cal", "T", "irc", 25.0, logistic(25)), ("R2", "H2", "cal", "T", "irc", 25.0, logistic(27))]
    res = analyze(_project(rows, cq_source="calculated"))
    assert res.calibration[("R2", "T")] - res.calibration[("R1", "T")] == pytest.approx(2.0, abs=0.1)


# --- thresholds ---


def test_auto_threshold_is_common_to_runs_of_one_instrument():
    res = analyze(_project(_plate("R1", (20, 22)) + _plate("R2", (30, 32))))
    assert res.curves[_key("R1", "A1")].threshold == res.curves[_key("R2", "A1")].threshold


def test_auto_threshold_is_per_instrument():
    p = _project(_plate("R1", (20, 22)) + _plate("R2", (30, 32), plateau=8.0, threshold=0.4))
    p.runs[1].instrument = "cfx"
    res = analyze(p)
    assert res.curves[_key("R1", "A1")].threshold != res.curves[_key("R2", "A1")].threshold


def test_manual_threshold_applies_to_its_run_only():
    p = _project(_plate("R1") + _plate("R2"))
    p.runs[0].thresholds["T"] = 0.2
    res = analyze(p)
    assert res.curves[_key("R1", "A1")].threshold == 0.2
    assert res.curves[_key("R2", "A1")].threshold != 0.2
    assert "thresholds_differ_no_irc" in _codes(res)


def test_one_threshold_raises_no_flag():
    assert "thresholds_differ_no_irc" not in _codes(analyze(_project(_plate("R1") + _plate("R2"))))


def test_flat_target_has_no_threshold_and_no_cq():
    p = _project([("R1", f"A{i}", f"s{i}", "T", "ntc", None, flat(noise=0.002, seed=i)) for i in range(4)])
    r = analyze(p).curves[_key("R1", "A1")]
    assert r.threshold is None and r.cq_calc is None and r.efficiency is None


# --- melt ---


def test_tm_in_results():
    rows = [(*r, melt(tm=84.0 + i * 0.1)) for i, r in enumerate(_plate())]
    r = analyze(_project(rows)).curves[_key("R1", "A2")]
    assert r.tms == pytest.approx((84.1,), abs=0.15)


def test_ready_derivative_is_not_differentiated_again():
    d = cv.melt_derivative(melt(tm=84.0))
    p = _project([("R1", "A1", "s", "T", "unknown", 22.0, None)])
    p.runs[0].wells["A1"].reactions[0].melt_derivative = d
    assert analyze(p).curves[_key("R1", "A1")].tms == pytest.approx((84.0,), abs=0.15)


def test_flat_ntc_melt_has_no_peaks():
    rows = [(*r, melt(tm=84.0)) for r in _plate()]
    rows.append(("R1", "H1", None, "T", "ntc", None, flat(noise=0.002), melt(height=0.0, noise=0.003)))
    assert analyze(_project(rows)).curves[_key("R1", "H1")].tms == ()


def test_small_shoulder_of_a_strong_target_is_not_a_peak():
    rows = [(*r, melt(tm=84.0)) for r in _plate()]
    rows.append(("R1", "B1", "s", "T", "unknown", None, logistic(25), melt(tm=84.0, second_tm=75.0, second_height=0.05)))
    assert analyze(_project(rows)).curves[_key("R1", "B1")].tms == pytest.approx((84.0,), abs=0.2)


# --- efficiency from curves ---


def _with_mode(project: Project, mode: str = "curves") -> Project:
    project.targets["T"].efficiency_mode = mode
    return project


def test_efficiency_from_curves():
    res = analyze(_with_mode(_project(_plate(cqs=range(18, 30)))))
    assert res.efficiency_source["T"] == "curves"
    assert res.efficiencies["T"] == pytest.approx(0.95, abs=0.05)


def test_curve_efficiency_is_shown_in_any_mode():
    res = analyze(_project(_plate(cqs=range(18, 30))))
    assert res.efficiency_source["T"] == "ideal"
    assert res.efficiencies["T"] == 1.0
    assert res.curve_efficiency["T"] == pytest.approx(0.95, abs=0.05)


def test_no_data_for_curves_mode_falls_back_to_ideal_with_a_flag():
    p = _with_mode(_project([("R1", "A1", "s", "T", "unknown", 25.0, None)]))
    p.targets["T"].efficiency_manual = 0.8
    res = analyze(p)
    assert "efficiency_curves_unusable" in _codes(res)
    assert res.efficiencies["T"] == 1.0 and res.efficiency_source["T"] == "ideal"


def test_curves_mode_checks_the_range():
    res = analyze(_with_mode(_project(_plate(cqs=range(18, 30), efficiency=0.75))))
    flag = next(f for f in res.flags if f.code == "efficiency_out_of_range")
    assert flag.target == "T" and flag.params["min"] == 0.90 and flag.params["max"] == 1.10


def test_subtracted_curves_are_marked_less_reliable():
    p = _with_mode(_project(_plate(cqs=range(18, 30))))
    for w in p.runs[0].wells.values():
        w.reactions[0].baseline_subtracted = True
    res = analyze(p)
    flag = next(f for f in res.flags if f.code == "efficiency_from_subtracted")
    assert flag.severity == "info"
    assert res.curves[_key("R1", "A1")].baseline_subtracted is True


def test_ntc_does_not_shape_efficiency():
    rows = _plate(cqs=range(18, 30)) + [("R1", "H1", None, "T", "ntc", None, logistic(33, efficiency=0.6))]
    assert analyze(_project(rows)).curve_efficiency["T"] == pytest.approx(0.95, abs=0.05)


def test_target_default_mode_is_unchanged():
    assert Target("x").efficiency_mode == "stdcurve"


# --- real files: nothing changes by default ---


def test_defaults_do_not_change_results_on_a_real_file():
    path = REAL / "appbio_quantstudio_designandanalysis_QS3_Relative_Quantification_example02.xlsx"
    run = import_file(path, "R1").run
    p = Project(runs=[run])
    p.ensure_targets_and_samples()
    res = analyze(p)
    for (sample, target), mean in res.mean_cq.items():
        rx = [
            r.cq
            for w in run.wells.values()
            if w.sample == sample
            for r in w.reactions
            if r.target == target and r.role == "unknown" and not r.excluded and r.cq is not None
        ]
        assert mean == pytest.approx(sum(rx) / len(rx))
    assert res.curves  # the curves were analysed all the same

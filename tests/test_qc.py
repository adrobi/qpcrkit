import pytest

from qpcr_core.qc import check_reactions
from tests.factories import make_project


def _codes(flags):
    return sorted(f.code for f in flags)


def _reps(cqs, role="unknown", target="IL6"):
    return make_project([("R1", f"A{i + 1}", "s1", target, role, cq, None) for i, cq in enumerate(cqs)])


def test_outlier_suggested_not_excluded():
    p = _reps([20.0, 20.1, 21.5])
    flags = check_reactions(p)
    assert _codes(flags) == ["outlier_suggested", "rep_sd_high"]
    sd = next(f for f in flags if f.code == "rep_sd_high")
    assert sd.severity == "warning"
    assert sd.params["sd"] == pytest.approx(0.8386497)
    assert sd.params["limit"] == 0.3
    out = next(f for f in flags if f.code == "outlier_suggested")
    assert out.coords == ("A3",)
    assert out.params == {"cq": 21.5, "median": 20.1}
    assert not any(r.excluded for _, _, r in p.iter_reactions())


def test_tight_replicates_clean():
    assert check_reactions(_reps([20.0, 20.1, 20.2])) == []


def test_partial_undetermined():
    assert _codes(check_reactions(_reps([20.0, None]))) == ["partial_undetermined"]


def test_two_replicates_no_outlier():
    assert _codes(check_reactions(_reps([20.0, 21.5]))) == ["rep_sd_high"]


@pytest.mark.parametrize("cq,expected", [(33.0, ["ntc_contamination"]), (None, []), (36.0, [])])
def test_ntc(cq, expected):
    flags = check_reactions(_reps([cq], role="ntc"))
    assert _codes(flags) == expected
    if expected:
        assert flags[0].severity == "error" and flags[0].coords == ("A1",)


def test_late_amplification():
    flags = check_reactions(_reps([35.0]))
    assert _codes(flags) == ["late_amplification"]
    assert flags[0].severity == "info"


def test_excluded_reactions_ignored():
    p = _reps([20.0, 20.1, 21.5])
    p.runs[0].wells["A3"].reactions[0].excluded = True
    assert check_reactions(p) == []


def test_standards_grouped_by_quantity():
    p = make_project([
        ("R1", "A1", None, "IL6", "std", 20.0, 100.0),
        ("R1", "A2", None, "IL6", "std", 20.05, 100.0),
        ("R1", "A3", None, "IL6", "std", 23.3, 10.0),
    ])
    assert check_reactions(p) == []


def test_wells_without_sample_are_not_replicates():
    p = make_project([("R1", f"A{i}", None, "SYBR", "unknown", 15.0 + i, None) for i in range(1, 10)])
    flags = check_reactions(p)
    assert _codes(flags) == ["wells_without_sample"]
    assert flags[0].severity == "info" and flags[0].params == {"count": 9}


def _nrt(sample_cq, nrt_cq):
    return make_project([
        ("R1", "A1", "s1", "IL6", "unknown", sample_cq, None),
        ("R1", "A2", "s1", "IL6", "unknown", sample_cq, None),
        ("R1", "A3", "s1", "IL6", "nrt", nrt_cq, None),
    ])


def test_nrt_amplified():
    flags = check_reactions(_nrt(25.0, 28.0))
    assert _codes(flags) == ["nrt_amplified"] and flags[0].severity == "warning"
    assert flags[0].coords == ("A3",) and flags[0].params == {"cq": 28.0, "delta": 5.0}


def test_nrt_far_enough_is_clean():
    assert check_reactions(_nrt(25.0, 33.0)) == []


def test_nrt_without_amplification_is_clean():
    assert check_reactions(_nrt(25.0, None)) == []


def test_nrt_with_sample_undetermined_is_flagged():
    assert _codes(check_reactions(_nrt(None, 30.0))) == ["nrt_amplified"]


def test_nrt_does_not_inflate_sample_spread():
    assert "rep_sd_high" not in _codes(check_reactions(_nrt(25.0, 28.0)))


def test_threshold_settings_reach_messages():
    from i18n import set_language, tr
    from qpcr_core.stdcurve import fit_std_curves

    set_language("en")
    p = make_project(
        [("R1", f"A{i}", None, "IL6", "std", 40 - 3.0 * __import__("math").log10(q), q) for i, q in enumerate((1e4, 1e3, 1e2))],
        eff_min=0.8,
        eff_max=1.05,
    )
    flag = next(f for f in fit_std_curves(p, lambda run, well, rxn: rxn.cq)[1] if f.code == "efficiency_out_of_range")
    text = tr("qc.efficiency_out_of_range", **flag.params)
    assert "80" in text and "105" in text


@pytest.mark.parametrize("role", ["pos", "irc"])
def test_unnamed_controls_are_still_checked(role):
    p = make_project([("R1", f"A{i}", None, "IL6", role, cq, None) for i, cq in enumerate((20.0, 21.0))])
    codes = _codes(check_reactions(p))
    assert "wells_without_sample" not in codes and "rep_sd_high" in codes

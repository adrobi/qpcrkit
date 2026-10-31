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

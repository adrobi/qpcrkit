import pytest

from qpcr_core.relquant import SampleRQ
from qpcr_core.stats import bh_adjust, compare, summarize

GROUPS = {"ctrl": [0.1, -0.2, 0.05, 0.0], "a": [1.9, 2.3, 2.1], "b": [0.6, 0.9, 0.4]}


def _rqs(groups=GROUPS, target="IL6"):
    out = []
    for g, values in groups.items():
        for i, v in enumerate(values):
            out.append(SampleRQ(f"{g}{i}", g, target, 20.0, 0.0, 2 ** v, v))
    return out


def _cmp(comparisons, a, b, test):
    return next(c for c in comparisons if (c.group_a, c.group_b, c.test) == (a, b, test))


def test_summarize():
    s = {g.group: g for g in summarize(_rqs())}
    assert s["ctrl"].n == 4
    assert s["ctrl"].mean_log2 == pytest.approx(-0.0125)
    assert s["ctrl"].sd_log2 == pytest.approx(0.1314978, rel=1e-6)
    assert s["ctrl"].sem_log2 == pytest.approx(0.0657489, rel=1e-6)
    assert s["ctrl"].ci95_log2 == pytest.approx(0.2092423, rel=1e-6)
    assert s["a"].ci95_log2 == pytest.approx(0.4968275, rel=1e-6)
    assert s["a"].fold == pytest.approx(2 ** 2.1)
    lo, hi = s["a"].fold_bounds("sd")
    assert lo == pytest.approx(2 ** 1.9) and hi == pytest.approx(2 ** 2.3)


def test_single_sample_group_bounds():
    s = summarize(_rqs({"x": [1.0]}))[0]
    assert s.sd_log2 is None and s.fold_bounds("sem") == (2.0, 2.0)


def test_welch_two_groups():
    comps, flags = compare(_rqs({"ctrl": GROUPS["ctrl"], "a": GROUPS["a"]}), "ctrl", "dunnett")
    c = _cmp(comps, "ctrl", "a", "welch")
    assert c.statistic == pytest.approx(-15.898183, rel=1e-6)
    assert c.p == pytest.approx(3.2475595e-4, rel=1e-6)
    assert flags == []


def test_anova_and_dunnett():
    comps, _ = compare(_rqs(), "ctrl", "dunnett")
    an = _cmp(comps, "*", "*", "anova")
    assert an.statistic == pytest.approx(105.480016, rel=1e-6)
    assert an.p == pytest.approx(5.936413e-6, rel=1e-5)
    # Dunnett p-values come from quasi-Monte-Carlo integration: tiny p only to absolute precision
    da, db = _cmp(comps, "ctrl", "a", "dunnett"), _cmp(comps, "ctrl", "b", "dunnett")
    assert da.statistic == pytest.approx(14.39203043, rel=1e-6)
    assert db.statistic == pytest.approx(4.39993041, rel=1e-6)
    assert da.p == pytest.approx(2.576e-7, abs=1e-5)
    assert db.p == pytest.approx(5.786e-3, rel=5e-2)


def test_tukey():
    comps, _ = compare(_rqs(), "ctrl", "tukey")
    assert _cmp(comps, "ctrl", "a", "tukey").p == pytest.approx(4.7728e-6, rel=1e-3)
    assert _cmp(comps, "ctrl", "b", "tukey").p == pytest.approx(7.7224e-3, rel=1e-3)
    assert _cmp(comps, "a", "b", "tukey").p == pytest.approx(8.4846e-5, rel=1e-3)


def test_bh_adjust():
    assert bh_adjust([0.01, 0.04, 0.03, 0.2]) == pytest.approx([0.04, 0.0533333, 0.0533333, 0.2], rel=1e-5)
    assert bh_adjust([]) == []


def test_too_few_bio_reps():
    comps, flags = compare(_rqs({"ctrl": GROUPS["ctrl"], "a": [2.0]}), "ctrl", "dunnett")
    assert comps == []
    assert [(f.severity, f.code, f.target, f.params) for f in flags] == [("info", "too_few_bio_reps", "IL6", {"group": "a"})]


def test_bh_across_targets():
    two = {"ctrl": GROUPS["ctrl"], "a": GROUPS["a"]}
    other = {"ctrl": GROUPS["ctrl"], "a": GROUPS["b"]}
    comps, _ = compare(_rqs(two, "IL6") + _rqs(other, "TNF"), "ctrl", "dunnett")
    ps = [c.p for c in comps]
    assert [c.p_adj for c in comps] == pytest.approx(bh_adjust(ps))

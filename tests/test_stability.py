"""Stability of reference genes: geNorm and NormFinder."""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest

from qpcr_core import stability as st

GENES = ["A", "B", "C", "D"]


def _by_definition_m(x: np.ndarray) -> np.ndarray:
    """M straight from Vandesompele 2002: mean SD of the log2 ratios with every other gene."""
    k = x.shape[1]
    out = []
    for j in range(k):
        sds = [np.std(x[:, j] - x[:, i], ddof=1) for i in range(k) if i != j]
        out.append(np.mean(sds))
    return np.array(out)


def _data(seed=1, n=6, k=4, spread=(0.1, 0.2, 0.4, 0.8)):
    rng = np.random.default_rng(seed)
    base = rng.normal(0, 1, n)[:, None]  # the amount of material differs between samples
    return base + np.column_stack([rng.normal(0, s, n) for s in spread[:k]])


# --- log2 quantities ---


def test_log2_quantities_with_ideal_efficiency():
    mean_cq = {("s1", "A"): 20.0, ("s2", "A"): 22.0, ("s3", "A"): 21.0, ("s1", "B"): 25.0, ("s2", "B"): 25.5, ("s3", "B"): 26.0}
    x, kept, excluded = st.log2_quantities(mean_cq, {"A": 1.0, "B": 1.0}, ["s1", "s2", "s3"], ["A", "B"])
    assert kept == ("s1", "s2", "s3") and excluded == ()
    assert x[:, 0] == pytest.approx([0.0, -2.0, -1.0])
    assert x[:, 1] == pytest.approx([0.0, -0.5, -1.0])


def test_log2_quantities_use_the_efficiency():
    mean_cq = {("s1", "A"): 20.0, ("s2", "A"): 22.0}
    x, _, _ = st.log2_quantities(mean_cq, {"A": 0.9}, ["s1", "s2"], ["A"])
    assert x[1, 0] == pytest.approx(-2.0 * math.log2(1.9))


def test_samples_without_a_cq_are_excluded():
    mean_cq = {("s1", "A"): 20.0, ("s2", "A"): None, ("s3", "A"): 21.0, ("s1", "B"): 25.0, ("s2", "B"): 25.0, ("s3", "B"): 26.0}
    x, kept, excluded = st.log2_quantities(mean_cq, {}, ["s1", "s2", "s3", "s4"], ["A", "B"])
    assert kept == ("s1", "s3") and excluded == ("s2", "s4")
    assert x.shape == (2, 2)
    assert x[:, 0] == pytest.approx([0.0, -1.0])  # the minimum is taken over the kept samples


# --- geNorm M ---


def test_m_matches_the_definition():
    x = _data()
    assert st.genorm_m(x) == pytest.approx(_by_definition_m(x), abs=1e-12)


def test_m_does_not_depend_on_the_scale_of_a_gene():
    x = _data()
    y = x.copy()
    y[:, 2] += 7.3  # another primer pair, another absolute level
    assert st.genorm_m(y) == pytest.approx(st.genorm_m(x), abs=1e-12)


def test_genes_in_perfect_agreement_have_m_zero():
    base = np.array([0.0, 1.0, -0.5, 2.0])
    x = np.column_stack([base, base + 3.0])
    assert st.genorm_m(x) == pytest.approx([0.0, 0.0])
    assert not np.isnan(st.genorm_m(x)).any()


def test_a_constant_gene_is_fine():
    x = np.column_stack([np.zeros(5), _data(n=5)[:, :2]])
    assert np.isfinite(st.genorm_m(x)).all()


@pytest.mark.parametrize("shape", [(5, 1), (2, 3)])
def test_too_little_data(shape):
    with pytest.raises(ValueError):
        st.genorm_m(np.zeros(shape))


# --- stepwise exclusion ---


def test_stepwise_exclusion():
    x = _data()
    ranking, steps = st.genorm_ranking(x, GENES)
    remaining = list(GENES)
    expected_removed = []
    for _ in range(len(GENES) - 2):
        cols = [GENES.index(g) for g in remaining]
        m = _by_definition_m(x[:, cols])
        assert dict(steps)[tuple(remaining)] == pytest.approx(m.mean())
        worst = remaining[int(np.argmax(m))]
        expected_removed.append(worst)
        remaining.remove(worst)
    assert ranking == tuple(sorted(remaining)) + tuple(reversed(expected_removed))
    assert [s[0] for s in steps][0] == tuple(GENES) and len(steps[-1][0]) == 2
    assert ranking[-1] == "D"  # the noisiest gene goes first


def test_ties_are_broken_by_name():
    base = np.array([0.0, 1.0, -0.5, 2.0])
    noise = np.array([0.3, -0.3, 0.3, -0.3])
    x = np.column_stack([base, base, base + noise, base - noise])
    ranking, _ = st.genorm_ranking(x, ["A", "B", "C", "D"])
    assert ranking[-1] == "D"  # C and D are equally bad; the later name goes first


# --- pairwise variation and the advice ---


def test_pairwise_variation():
    x = _data()
    ranking, _ = st.genorm_ranking(x, GENES)
    v = st.pairwise_v(x, GENES, ranking)
    assert set(v) == {2, 3}
    for n in (2, 3):
        cols_n = [GENES.index(g) for g in ranking[:n]]
        cols_n1 = [GENES.index(g) for g in ranking[: n + 1]]
        expected = np.std(x[:, cols_n].mean(axis=1) - x[:, cols_n1].mean(axis=1), ddof=1)
        assert v[n] == pytest.approx(expected)


def test_no_pairwise_variation_with_two_genes():
    x = _data(k=2)
    assert st.pairwise_v(x, ["A", "B"], ("A", "B")) == {}


@pytest.mark.parametrize(
    "v,expected,found",
    [
        ({2: 0.10, 3: 0.05}, ("A", "B"), True),
        ({2: 0.20, 3: 0.12}, ("A", "B", "C"), True),
        ({2: 0.20, 3: 0.18}, ("A", "B", "C", "D"), False),
        ({}, ("A", "B"), True),
    ],
)
def test_recommend(v, expected, found):
    ranking = ("A", "B", "C", "D")[: 2 if not v else 4]
    assert st.recommend(ranking, v) == (expected, found)

"""Analysis of raw curves: baseline, Cq, efficiency, melt."""

from __future__ import annotations

import math

import numpy as np
import pytest

from qpcr_core import curves as cv
from qpcr_core.models import Curve
from tests.curve_factory import flat, logistic


def _at(curve: Curve, cycle: int) -> float:
    return curve.y[curve.x.index(float(cycle))]


# --- clean ---


def test_clean_drops_nan_and_sorts():
    c = cv.clean(Curve([3, 1, 2, 4, 5, 6], [3.0, 1.0, math.nan, 4.0, 5.0, 6.0]))
    assert c.x == (1.0, 3.0, 4.0, 5.0, 6.0)
    assert c.y == (1.0, 3.0, 4.0, 5.0, 6.0)


@pytest.mark.parametrize(
    "bad",
    [
        None,
        Curve([1, 2, 3], [1.0, 2.0, 3.0]),
        Curve([1, 2, 3, 4, 5, 6], [1.0, 2.0, 3.0]),
        Curve([1, 2, 3, 4, 5, 6], [math.nan] * 6),
    ],
)
def test_clean_rejects_unusable_curves(bad):
    assert cv.clean(bad) is None


# --- baseline ---


def test_baseline_removes_drift():
    out = cv.subtract_baseline(logistic(25, drift=0.002))
    assert np.mean([_at(out, c) for c in range(3, 11)]) == pytest.approx(0, abs=0.01)
    assert _at(out, 15) == pytest.approx(0, abs=0.01)  # the slope is gone, not only the level
    assert _at(out, 25) == pytest.approx(0.1, abs=0.01)


def test_baseline_with_noise_keeps_the_signal():
    out = cv.subtract_baseline(logistic(22, drift=0.002, noise=0.002))
    assert _at(out, 22) == pytest.approx(0.1, abs=0.01)


def test_already_subtracted_only_loses_the_offset():
    out = cv.subtract_baseline(logistic(25, background=3.0, subtracted=True), already_subtracted=True)
    assert np.mean([_at(out, c) for c in range(3, 11)]) == pytest.approx(0, abs=0.01)
    assert _at(out, 25) == pytest.approx(0.1, abs=0.01)


def test_early_cq_keeps_the_signal():
    out = cv.subtract_baseline(logistic(7))
    assert cv.has_amplification(out)
    assert _at(out, 7) == pytest.approx(0.1, abs=0.03)
    assert out.y[-1] == pytest.approx(2.0, abs=0.1)


def test_negative_early_values_stay_amplified():
    out = cv.subtract_baseline(logistic(24, background=-1.0, noise=0.002, subtracted=True), already_subtracted=True)
    assert cv.has_amplification(out)
    assert _at(out, 24) == pytest.approx(0.1, abs=0.01)


def test_no_growth_uses_the_whole_curve():
    out = cv.subtract_baseline(flat(drift=0.002, noise=0.001))
    assert np.abs(out.y).max() < 0.005


def test_noise_estimate():
    out = cv.subtract_baseline(logistic(30, noise=0.002))
    assert cv.baseline_noise(out) == pytest.approx(0.002, rel=0.5)


def test_noise_is_positive_on_a_noiseless_curve():
    assert cv.baseline_noise(cv.subtract_baseline(logistic(25))) > 0


# --- amplification ---


@pytest.mark.parametrize(
    "curve,expected",
    [
        (logistic(22), True),
        (logistic(22, noise=0.002), True),
        (logistic(38, noise=0.002), True),
        (flat(noise=0.002), False),
        (flat(drift=0.002), False),
        (flat(drift=0.002, noise=0.002), False),
        (flat(), False),
    ],
)
def test_has_amplification(curve, expected):
    assert cv.has_amplification(cv.subtract_baseline(curve)) is expected


def test_single_spike_is_not_amplification():
    y = list(flat(noise=0.002).y)
    y[29] += 1.0
    c = Curve(list(range(1, 41)), y)
    assert cv.has_amplification(cv.subtract_baseline(c)) is False


def test_thermal_bend_is_not_amplification():
    """A smooth noiseless bend of a fraction of a percent of the background is not a product."""
    x = np.arange(1.0, 41.0)
    y = 1000.0 + 0.5 * np.tanh((x - 25) / 3)
    assert cv.is_amplified(Curve(x.tolist(), y.tolist())) is False


def test_is_amplified_on_raw_curve():
    assert cv.is_amplified(logistic(25, background=1000.0, plateau=500.0, threshold=10.0)) is True


@pytest.mark.parametrize(
    "curve",
    [
        Curve([1, 2, 3, 4, 5], [1.0] * 5),
        Curve(list(range(1, 41)), [5.0] * 40),
        Curve(list(range(1, 7)), [0.0, 0.0, 0.0, 0.0, 0.0, 1.0]),
    ],
)
def test_short_or_constant_curves_do_not_raise(curve):
    out = cv.subtract_baseline(cv.clean(curve))
    assert cv.has_amplification(out) is False

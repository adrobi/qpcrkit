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


# --- threshold and Cq ---


def _set(cqs, **kw):
    return [cv.subtract_baseline(logistic(c, seed=i, **kw)) for i, c in enumerate(cqs)]


@pytest.mark.parametrize("noise,tolerance", [(0.0, 0.02), (0.0005, 0.05), (0.002, 0.15)])
def test_threshold_keeps_differences_between_curves(noise, tolerance):
    cqs = [18, 22, 26, 30]
    curves = _set(cqs, noise=noise)
    t = cv.auto_threshold(curves)
    got = [cv.cq_at(c, t) for c in curves]
    for a, b, ca, cb in zip(got, got[1:], cqs, cqs[1:]):
        assert b - a == pytest.approx(cb - ca, abs=tolerance)


def test_cq_at_true_threshold():
    assert cv.cq_at(cv.subtract_baseline(logistic(24.3)), 0.1) == pytest.approx(24.3, abs=0.1)


def test_threshold_above_plateau_gives_no_cq():
    assert cv.cq_at(cv.subtract_baseline(logistic(24)), 50.0) is None


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_threshold_must_be_positive(bad):
    with pytest.raises(ValueError):
        cv.cq_at(logistic(24), bad)


def test_crossing_on_the_last_cycles_counts():
    c = Curve(list(range(1, 41)), [0.001] * 38 + [0.05, 0.3])
    assert cv.cq_at(c, 0.1) == pytest.approx(39 + np.log(2) / np.log(6), abs=1e-6)
    assert cv.cq_at(Curve(list(range(1, 41)), [0.001] * 39 + [0.3]), 0.1) is not None


def test_non_positive_value_before_crossing_interpolates_linearly():
    c = Curve([1, 2, 3, 4, 5, 6], [-0.1, -0.1, -0.1, 0.3, 0.6, 1.2])
    assert cv.cq_at(c, 0.1) == pytest.approx(3.5)


def test_short_spike_is_not_a_crossing():
    y = [0.0] * 40
    y[14] = 0.5
    y[35:] = [0.05, 0.2, 0.4, 0.8, 1.0]
    assert cv.cq_at(Curve(list(range(1, 41)), y), 0.1) == pytest.approx(36 + np.log(2) / np.log(4), abs=1e-6)


def test_late_curve_does_not_pull_the_threshold_below_noise():
    curves = _set([20, 20, 20, 37.5], noise=0.01, plateau=0.25, threshold=0.05)
    noise = np.median([cv.baseline_noise(c) for c in curves if cv.has_amplification(c)])
    assert cv.auto_threshold(curves) >= 10 * noise * 0.999


def test_flat_curves_have_no_threshold():
    assert cv.auto_threshold([cv.subtract_baseline(flat(noise=0.002, seed=i)) for i in range(4)]) is None
    assert cv.auto_threshold([]) is None


def test_noise_below_threshold_does_not_cross():
    assert cv.cq_at(cv.subtract_baseline(flat(noise=0.002)), 0.1) is None


def test_plateau_that_decays_later_is_still_amplification():
    """Seen on a real StepOne well: the signal rises at cycle 10 and falls to a tenth by the end."""
    y = [1.0, 0.9, 1.7, 3.7, 5.8, -1.7, -1.4, 6.3, 4.4, 24.5, 46.7, 79.0, 106.2, 122.3, 126.8, 123.8, 118.5, 113.1]
    y += [104.8, 101.0, 97.8, 97.4, 91.7, 85.6, 80.1, 76.9, 72.0, 67.3, 61.8, 57.1, 51.8, 47.6, 43.2, 36.3, 33.4, 28.9]
    y += [26.5, 20.3, 16.7, 14.1]
    assert cv.is_amplified(Curve(list(range(1, 41)), y), already_subtracted=True) is True


def test_decay_of_the_first_cycles_is_not_the_growth():
    """Seen on LC96: the signal falls along a curve for a long time before a late rise."""
    grown = logistic(34, plateau=20.0, threshold=1.0, cycles=50, background=0.0)
    decay = 2.0 * np.exp(-(np.array(grown.x) - 1) / 4)
    c = Curve(grown.x, (np.array(grown.y) + decay + 20.0).tolist())
    assert cv._baseline_window(c)[1] > 20
    assert cv.cq_at(cv.subtract_baseline(c), 1.0) == pytest.approx(34, abs=0.3)

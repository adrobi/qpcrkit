"""Analysis of raw curves: baseline, amplification, threshold and Cq, efficiency, melt peaks."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy.signal import savgol_filter

from .models import Curve

_MIN_POINTS = 5
_SKIP = 2  # the first cycles carry lamp and mixing artefacts
_FIRST_LINE_END = 8  # cycles 3..8 give the first estimate of the background line
_MIN_LINE_POINTS = 6  # fewer points cannot tell a drift from the start of the exponent
_MIN_SIGNAL = 1e-3  # flat curves leave rounding residue, not a signal
_MIN_RISE = 0.01  # of the background level, for a raw signal


def _mad(values: np.ndarray) -> float:
    return float(np.median(np.abs(values - np.median(values)))) if values.size else 0.0


def clean(curve: Curve | None) -> Curve | None:
    """Finite points sorted by x; None when too few remain or the axes differ in length."""
    if curve is None or len(curve.x) != len(curve.y):
        return None
    x, y = np.asarray(curve.x, dtype=float), np.asarray(curve.y, dtype=float)
    keep = np.isfinite(x) & np.isfinite(y)
    if keep.sum() < _MIN_POINTS:
        return None
    x, y = x[keep], y[keep]
    order = np.argsort(x, kind="stable")
    return Curve(x[order].tolist(), y[order].tolist())


def _second_derivative(y: np.ndarray) -> np.ndarray:
    window = 7 if y.size >= 7 else 5
    return savgol_filter(y, window, 2, deriv=2)


def _sdm_index(y: np.ndarray) -> int | None:
    """Where the exponent is fastest to accelerate; None when nothing stands out of the noise."""
    d2 = _second_derivative(y)
    i = int(np.argmax(d2[_SKIP:])) + _SKIP
    if d2[i] <= 8 * _mad(d2) + 1e-9 * float(np.ptp(y)):
        return None
    return i


@lru_cache(maxsize=8192)
def _baseline_window(curve: Curve) -> tuple[int, int]:
    """Indexes [start, end) of the cycles before the growth."""
    y = np.asarray(curve.y, dtype=float)
    x = np.asarray(curve.x, dtype=float)
    i_sdm = _sdm_index(y)
    if i_sdm is None:
        return _SKIP, y.size
    end = i_sdm - 3  # exclusive: the last baseline point is four cycles before the acceleration peak
    if end - _SKIP < _MIN_LINE_POINTS:
        return _SKIP, _SKIP + 2  # a very early Cq: a slope here would be the exponent itself
    line = np.polyfit(x[_SKIP:_FIRST_LINE_END], y[_SKIP:_FIRST_LINE_END], 1)
    residual = y - np.polyval(line, x)
    limit = max(5 * _mad(residual[_SKIP:_FIRST_LINE_END]), 1e-4 * float(np.ptp(y)))
    for i in range(_FIRST_LINE_END, end):
        if (residual[i : i + 3] > limit).all():
            return _SKIP, i
    return _SKIP, end


def subtract_baseline(curve: Curve, already_subtracted: bool = False) -> Curve:
    y = np.asarray(curve.y, dtype=float)
    x = np.asarray(curve.x, dtype=float)
    start, end = _baseline_window(curve)
    if already_subtracted:
        y = y - float(np.mean(y[start:end]))
    elif end - start < _MIN_LINE_POINTS:
        y = y - float(np.median(y[start:end]))
    else:
        y = y - np.polyval(np.polyfit(x[start:end], y[start:end], 1), x)
    return Curve(curve.x, y.tolist())


def baseline_noise(curve: Curve) -> float:
    """SD of the cycles before the growth; never zero, so a threshold can be built on it."""
    y = np.asarray(curve.y, dtype=float)
    start, end = _baseline_window(curve)
    return max(float(np.std(y[start:end])), 1e-9 * float(np.ptp(y)))


def has_amplification(curve: Curve) -> bool:
    """``curve`` has its background removed."""
    y = np.asarray(curve.y, dtype=float)
    top = float(y.max())
    steps = np.diff(y)
    if top <= max(10 * baseline_noise(curve), _MIN_SIGNAL) or top <= 8 * _mad(steps):
        return False
    steepest = int(np.argmax(steps))
    left = steepest
    while left > 0 and steps[left - 1] > 0:
        left -= 1
    right = steepest
    while right + 1 < steps.size and steps[right + 1] > 0:
        right += 1
    if right - left + 1 < 4:
        return False
    return bool(y[-1] >= 0.5 * top)  # a lone spike does not stay up


def is_amplified(raw: Curve, already_subtracted: bool = False) -> bool:
    """On a raw signal: a smooth bend of a fraction of the background is not a product."""
    out = subtract_baseline(raw, already_subtracted)
    if not has_amplification(out):
        return False
    if already_subtracted:
        return True
    start, end = _baseline_window(raw)
    level = abs(float(np.mean(raw.y[start:end])))
    return max(out.y) > _MIN_RISE * level

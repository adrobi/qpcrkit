"""Analysis of raw curves: baseline, amplification, threshold and Cq, efficiency, melt peaks."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import find_peaks, savgol_filter

from .models import Curve

_MIN_POINTS = 5
USABLE_EFFICIENCY = (0.5, 1.5)  # outside this a curve is broken (e.g. swapped quantities), not just poor
_SKIP = 2  # the first cycles carry lamp and mixing artefacts
_MIN_LINE_POINTS = 6  # fewer points cannot tell a drift from the start of the exponent
_LOCAL_LINE_POINTS = 10
_MIN_SIGNAL = 1e-6  # flat curves leave rounding residue, not a signal; some instruments report thousandths
_MIN_RISE = 0.01  # of the background level, for a raw signal
MELT_NOISE_FACTOR = 10  # prominence is peak to valley: noise alone reaches 5 SD of it
_MELT_NOISE_WINDOW_C = 15.0
_MELT_MIN_DISTANCE_C = 1.5
_D2_NOISE_GAIN = {5: 0.5345, 7: 0.2182}  # norm of the Savitzky-Golay coefficients


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


def _point_noise(y: np.ndarray) -> float:
    """SD of the noise of one point, from the smallest second differences.

    A drift has none, and the growth, which can take half of the curve, stays out of the lower quartile.
    """
    return float(np.percentile(np.abs(np.diff(y, 2)), 25)) / 0.3186 / np.sqrt(6)


def _sdm_index(y: np.ndarray) -> int | None:
    """Where the rising signal accelerates most; None when nothing stands out of the noise.

    Only rising points count: the decay of the first cycles is convex too.
    """
    window = 7 if y.size >= 7 else 5
    d2 = savgol_filter(y, window, 2, deriv=2)
    rising = savgol_filter(y, window, 2, deriv=1) > 0
    rising[: _SKIP] = False
    if not rising.any():
        return None
    i = int(np.argmax(np.where(rising, d2, -np.inf)))
    return i if d2[i] > max(5 * _D2_NOISE_GAIN[window] * _point_noise(y), 1e-9 * float(np.ptp(y))) else None


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
    noise = _point_noise(y)
    limit = max(noise, 1e-4 * float(np.ptp(y)))
    while end - _SKIP > _MIN_LINE_POINTS:
        # The last points are judged by a line fitted without them, or they would tilt it towards themselves,
        # and only by the nearest cycles: an early decay would pass for growth.
        start = max(_SKIP, end - 2 - _LOCAL_LINE_POINTS)
        line = np.polyfit(x[start : end - 2], y[start : end - 2], 1)
        if y[end - 1] <= y[end - 3] or (y[end - 2 : end] - np.polyval(line, x[end - 2 : end])).min() <= limit:
            break  # not rising here, or back on the line
        end -= 1
    end = max(end - 2, _SKIP + _MIN_LINE_POINTS)  # the signal is about as large as the noise where the check stops
    return _trim_decay(x, y, end, limit), end


def _trim_decay(x: np.ndarray, y: np.ndarray, end: int, limit: float) -> int:
    """Drop first cycles while the window is not a line: the signal often decays along a curve at the start."""
    start = _SKIP
    while end - start > _MIN_LINE_POINTS:
        residual = y[start:end] - np.polyval(np.polyfit(x[start:end], y[start:end], 1), x[start:end])
        if float(np.std(residual)) <= 1.5 * limit:
            break
        start += 1
    return start


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
    # Reaches a plateau or is still growing at the end; a lone spike does neither. The plateau may decay later.
    return bool(y[-1] >= 0.5 * top or (y >= 0.5 * top).sum() >= 4)


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


def auto_threshold(curves: list[Curve]) -> float | None:
    """One threshold for a target, in the log-linear part of its growing curves (background removed)."""
    growing = [c for c in curves if has_amplification(c)]
    if not growing:
        return None
    lower = 10 * float(np.median([baseline_noise(c) for c in growing]))
    upper = float(np.percentile([max(c.y) for c in growing], 25)) / 4
    return lower if lower >= upper else float(np.sqrt(lower * upper))


def cq_at(curve: Curve, threshold: float) -> float | None:
    """The fractional cycle of the first stable crossing."""
    if threshold <= 0:
        raise ValueError("threshold must be positive")
    x, y = curve.x, curve.y
    for i in range(1, len(y)):
        if y[i - 1] > threshold or y[i] <= threshold:
            continue
        if not all(y[j] > threshold for j in range(i, min(i + 3, len(y)))):
            continue
        if y[i - 1] > 0:
            part = np.log(threshold / y[i - 1]) / np.log(y[i] / y[i - 1])
        else:
            part = (threshold - y[i - 1]) / (y[i] - y[i - 1])
        return float(x[i - 1] + part * (x[i] - x[i - 1]))
    return None


def efficiency_window(curves: list[Curve]) -> tuple[float, float] | None:
    """One band of signal for a target, as in LinRegPCR: from above the noise to where the exponent starts to slow."""
    growing = [c for c in curves if has_amplification(c)]
    tops = []
    for c in growing:
        i = _sdm_index(np.asarray(c.y, dtype=float))
        if i is not None:
            tops.append(c.y[i])
    if not tops:
        return None
    upper = float(np.median(tops))
    lower = max(upper / 32, 4 * float(np.median([baseline_noise(c) for c in growing])))
    return (lower, upper) if lower < upper else None


def _fit_log(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    logy = np.log10(y)
    slope, intercept = np.polyfit(x, logy, 1)
    total = float(np.sum((logy - logy.mean()) ** 2))
    r2 = 1 - float(np.sum((logy - (slope * x + intercept)) ** 2)) / total if total else 0.0
    return float(10**slope - 1), r2


def well_efficiency(curve: Curve, window: tuple[float, float]) -> tuple[float, float] | None:
    """(E, R²) over the longest unbroken run of points inside the band."""
    x, y = np.asarray(curve.x, dtype=float), np.asarray(curve.y, dtype=float)
    low, high = window
    best: tuple[int, int] = (0, 0)
    i = 0
    while i < y.size:
        if low <= y[i] <= high:
            j = i
            while j + 1 < y.size and low <= y[j + 1] <= high:
                j += 1
            if j - i + 1 > best[1] - best[0]:
                best = (i, j + 1)
            i = j + 1
        else:
            i += 1
    start, end = best
    if end - start < 3:
        return None
    if end - start == 3:  # a steep curve jumps across the band: one more point from below, if it holds the line
        if start == 0 or y[start - 1] <= 5 * baseline_noise(curve):
            return None
        e, r2 = _fit_log(x[start - 1 : end], y[start - 1 : end])
        return (e, r2) if r2 >= 0.99 else None
    return _fit_log(x[start:end], y[start:end])


def target_efficiency(results: list[tuple[float, float]], min_r2: float = 0.99) -> float | None:
    """Median over the wells that fit a line and give a believable efficiency."""
    good = [e for e, r2 in results if r2 >= min_r2 and USABLE_EFFICIENCY[0] <= e <= USABLE_EFFICIENCY[1]]
    return float(np.median(good)) if good else None


def melt_derivative(curve: Curve, window_c: float = 1.25) -> Curve:
    """-dF/dT, smoothed over a window given in degrees: instruments step from 0.05 to 0.5 °C."""
    x, y = np.asarray(curve.x, dtype=float), np.asarray(curve.y, dtype=float)
    step = float(np.median(np.diff(x)))
    points = int(round(window_c / step)) | 1
    points = min(max(points, 5), y.size if y.size % 2 else y.size - 1)
    return Curve(curve.x, (-savgol_filter(y, points, 2, deriv=1, delta=step)).tolist())


def melt_noise(derivative: Curve) -> float:
    """SD around a wide running median: peaks and a sloping background do not count as noise."""
    x, y = np.asarray(derivative.x, dtype=float), np.asarray(derivative.y, dtype=float)
    size = int(round(_MELT_NOISE_WINDOW_C / float(np.median(np.diff(x))))) | 1
    return 1.4826 * _mad(y - median_filter(y, size=size, mode="nearest"))


def melt_peaks(derivative: Curve, min_height: float) -> list[float]:
    """Tm of the significant peaks, highest first; the top is refined by a parabola through 3 points."""
    x, y = np.asarray(derivative.x, dtype=float), np.asarray(derivative.y, dtype=float)
    step = float(np.median(np.diff(x)))
    distance = max(1, int(round(_MELT_MIN_DISTANCE_C / step)))
    peaks, _ = find_peaks(y, height=min_height, prominence=min_height, distance=distance)
    out: list[tuple[float, float]] = []
    for i in peaks:
        a, b, c = y[i - 1], y[i], y[i + 1]
        bend = a - 2 * b + c
        shift = 0.5 * (a - c) / bend if bend else 0.0
        out.append((float(b), float(x[i] + shift * step)))
    return [t for _, t in sorted(out, reverse=True)]

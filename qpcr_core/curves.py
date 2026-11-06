"""Analysis of raw curves: baseline, amplification, threshold and Cq, efficiency, melt peaks."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import find_peaks, savgol_filter

from .flags import Flag
from .models import Curve, Project, Reaction, Run, Settings, Well

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
    x, y = x[order], y[order]
    if (np.diff(x) <= 0).any():  # two values for one cycle or temperature: nothing tells which is right
        return None
    return Curve(x.tolist(), y.tolist())


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
    else:
        return _SKIP, _SKIP + 2  # still rising at the shortest line: the growth starts inside the first cycles
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
    size = min(max(size, 3), y.size if y.size % 2 else y.size - 1)
    noise = 1.4826 * _mad(y - median_filter(y, size=size, mode="nearest"))
    return max(noise, _MIN_SIGNAL, 1e-9 * float(np.ptp(y)))  # a noiseless curve still has rounding ripples


def melt_peaks(derivative: Curve, min_height: float) -> list[float]:
    """Tm of the significant peaks, highest first."""
    return [tm for _, tm in _melt_peak_list(derivative, min_height)]


def _melt_peak_list(derivative: Curve, min_height: float) -> list[tuple[float, float]]:
    """(height, Tm), highest first; the top is refined by a parabola through 3 points."""
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
    return sorted(out, reverse=True)


# --- one project ---

CurveKey = tuple[str, str, str, str]  # run_id, coord, target, fluor


@dataclass(frozen=True)
class CurveResult:
    cq_calc: float | None
    efficiency: float | None
    window_r2: float | None
    tms: tuple[float, ...]
    threshold: float | None
    baseline_subtracted: bool


def run_uses_calculated(run: Run, settings: Settings) -> bool:
    """Our Cq on request, or when the instrument gave none: the source is chosen for a whole run."""
    if settings.cq_source == "calculated":
        return True
    return not any(r.cq is not None for w in run.wells.values() for r in w.reactions)


@lru_cache(maxsize=8192)
def _amplification_view(curve: Curve, already_subtracted: bool) -> tuple[Curve, bool] | None:
    """The curve without its background and whether it amplified; None when it cannot be used."""
    usable = clean(curve)
    if usable is None:
        return None
    try:
        return subtract_baseline(usable, already_subtracted), is_amplified(usable, already_subtracted)
    except (ValueError, np.linalg.LinAlgError):
        return None


@lru_cache(maxsize=8192)
def _melt_view(curve: Curve, ready_derivative: bool) -> tuple[Curve, float] | None:
    """-dF/dT and its noise."""
    usable = clean(curve)
    if usable is None:
        return None
    try:
        derivative = usable if ready_derivative else melt_derivative(usable)
        return derivative, melt_noise(derivative)
    except ValueError:
        return None


def _melt_of(rxn: Reaction) -> tuple[Curve, float] | None:
    if rxn.melt is not None:
        return _melt_view(rxn.melt, False)
    return _melt_view(rxn.melt_derivative, True) if rxn.melt_derivative is not None else None


def subtracted_curve(rxn: Reaction) -> Curve | None:
    """The amplification curve as it is analysed, without its background."""
    if rxn.amplification is None:
        return None
    view = _amplification_view(rxn.amplification, rxn.baseline_subtracted)
    return view[0] if view else None


def derivative_curve(rxn: Reaction) -> Curve | None:
    """-dF/dT, from the raw melt or the instrument's own derivative."""
    view = _melt_of(rxn)
    return view[0] if view else None


def analyze_curves(project: Project) -> tuple[dict[CurveKey, CurveResult], list[Flag]]:
    views: dict[CurveKey, tuple[Curve, bool] | None] = {}
    by_target: dict[tuple[str, str], list[Curve]] = defaultdict(list)
    unusable: dict[str, list[str]] = defaultdict(list)
    for run, well, rxn in project.iter_reactions():
        has_melt = rxn.melt is not None or rxn.melt_derivative is not None
        if has_melt and _melt_of(rxn) is None:
            unusable[run.id].append(well.coord)
        if rxn.amplification is None:
            continue
        view = views[(run.id, well.coord, rxn.target, rxn.fluor)] = _amplification_view(rxn.amplification, rxn.baseline_subtracted)
        if view is None:
            unusable[run.id].append(well.coord)
        elif not rxn.excluded and rxn.role != "ntc":
            by_target[(run.instrument, rxn.target)].append(view[0])
    thresholds = {k: auto_threshold(v) for k, v in by_target.items()}
    windows = {k: efficiency_window(v) for k, v in by_target.items()}

    # Peak height that counts: from the amplified reactions of a target on its run, so an NTC is judged by them.
    main_peaks: dict[tuple[str, str], list[float]] = defaultdict(list)
    for run, well, rxn in project.iter_reactions():
        view = views.get((run.id, well.coord, rxn.target, rxn.fluor))
        amplified = view[1] if view else rxn.cq is not None
        melt = _melt_of(rxn)
        if melt and amplified and not rxn.excluded and rxn.role != "ntc":
            peaks = _melt_peak_list(melt[0], MELT_NOISE_FACTOR * melt[1])
            if peaks:
                main_peaks[(run.id, rxn.target)].append(peaks[0][0])

    results: dict[CurveKey, CurveResult] = {}
    for run, well, rxn in project.iter_reactions():
        melt = _melt_of(rxn)
        if rxn.amplification is None and rxn.melt is None and rxn.melt_derivative is None:
            continue
        key = (run.id, well.coord, rxn.target, rxn.fluor)
        view = views.get(key)
        group = (run.instrument, rxn.target)
        manual = run.thresholds.get(rxn.target)
        threshold = manual if manual is not None and manual > 0 else thresholds.get(group)
        cq = e = r2 = None
        if view is not None and view[1]:
            cq = cq_at(view[0], threshold) if threshold else None
            window = windows.get(group)
            fitted = well_efficiency(view[0], window) if window else None
            if fitted:
                e, r2 = fitted
        tms: tuple[float, ...] = ()
        if melt is not None:
            heights = main_peaks.get((run.id, rxn.target))
            floor = 0.1 * float(np.median(heights)) if heights else 0.0
            tms = tuple(melt_peaks(melt[0], max(MELT_NOISE_FACTOR * melt[1], floor)))
        results[key] = CurveResult(cq, e, r2, tms, threshold, rxn.baseline_subtracted)
    flags = [
        Flag("warning", "curve_unusable", {"count": len(set(c))}, run_id, tuple(dict.fromkeys(c)))
        for run_id, c in unusable.items()
    ]
    return results, flags


def target_efficiencies(project: Project, results: dict[CurveKey, CurveResult]) -> dict[str, float]:
    """The efficiency of each target from its curves, without NTC and excluded reactions."""
    fitted: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for run, well, rxn in project.iter_reactions():
        result = results.get((run.id, well.coord, rxn.target, rxn.fluor))
        if result and result.efficiency is not None and not rxn.excluded and rxn.role != "ntc":
            fitted[rxn.target].append((result.efficiency, result.window_r2))
    out = {t: target_efficiency(v) for t, v in fitted.items()}
    return {t: e for t, e in out.items() if e is not None}


def source_flags(project: Project, results: dict[CurveKey, CurveResult], factors: dict[tuple[str, str], float]) -> list[Flag]:
    """Warnings about where the Cq of each run came from; they depend on whether runs are calibrated."""
    flags: list[Flag] = []
    sources: dict[str, set[bool]] = defaultdict(set)
    thresholds: dict[str, set[float]] = defaultdict(set)
    for run in project.runs:
        calculated = run_uses_calculated(run, project.settings)
        without = []
        with_curve = False
        compared: set[str] = set()  # an NTC or an excluded reaction takes no part in any comparison
        for well in run.wells.values():
            for rxn in well.reactions:
                if rxn.excluded:
                    continue
                result = results.get((run.id, well.coord, rxn.target, rxn.fluor))
                if rxn.role != "ntc":
                    compared.add(rxn.target)
                    if calculated and result is not None and result.threshold is not None:
                        thresholds[rxn.target].add(result.threshold)
                if rxn.amplification is None:
                    without.append(well.coord)
                else:
                    with_curve = True
        if calculated and without and (with_curve or project.settings.cq_source == "calculated"):
            flags.append(Flag("warning", "no_curve_for_calculated", {"count": len(without)}, run.id, tuple(without)))
        if not calculated or with_curve:  # a plate with neither Cq nor curves gives no Cq to mix
            for target in compared:
                sources[target].add(calculated)
    for target, kinds in sources.items():
        if len(kinds) > 1:
            severity = "warning" if any(k[1] == target for k in factors) else "error"
            flags.append(Flag(severity, "mixed_cq_sources", target=target))
    for target, values in thresholds.items():
        if len(values) > 1 and not any(k[1] == target for k in factors):
            flags.append(Flag("warning", "thresholds_differ_no_irc", target=target))
    return flags


def curve_flags(
    project: Project,
    results: dict[CurveKey, CurveResult],
    raw_cq_of: Callable[[Run, Well, Reaction], float | None],
) -> list[Flag]:
    """Checks a Cq table cannot make. Everything is compared within a run and a target."""
    s = project.settings
    flags: list[Flag] = []
    groups: dict[tuple[str, str], list[tuple[Well, Reaction, CurveResult]]] = defaultdict(list)
    silent: dict[tuple[str, str], list[str]] = defaultdict(list)
    for run, well, rxn in project.iter_reactions():
        if rxn.excluded:
            continue
        cq = raw_cq_of(run, well, rxn)
        if cq is not None and cq < s.early_cq and rxn.role not in ("std", "pos", "ntc"):
            flags.append(Flag("warning", "early_cq", {"cq": cq, "min": s.early_cq}, run.id, (well.coord,), rxn.target, well.sample))
        view = _amplification_view(rxn.amplification, rxn.baseline_subtracted) if rxn.amplification is not None else None
        if rxn.cq is not None and view is not None and not view[1]:
            silent[(run.id, rxn.target)].append(well.coord)
        result = results.get((run.id, well.coord, rxn.target, rxn.fluor))
        if result is not None:
            groups[(run.id, rxn.target)].append((well, rxn, result))
    flags += [
        Flag("warning", "no_amplification_with_cq", {"count": len(c)}, run_id, tuple(c), target)
        for (run_id, target), c in silent.items()
    ]
    for (run_id, target), rows in groups.items():
        flags += _melt_flags(s, run_id, target, rows)
        flags += _disagreement_flags(s, run_id, target, rows)
    return flags


def _melt_flags(s: Settings, run_id: str, target: str, rows: list[tuple[Well, Reaction, CurveResult]]) -> list[Flag]:
    flags: list[Flag] = []
    products = [r for r in rows if r[1].role != "ntc" and r[2].tms and (r[2].cq_calc is not None or r[1].cq is not None)]
    median = float(np.median([r[2].tms[0] for r in products])) if products else None
    for well, rxn, result in rows:
        if rxn.role == "ntc":
            for tm in result.tms:
                near = median is not None and abs(tm - median) <= s.tm_shift_max
                code, severity = ("ntc_melt_product", "error") if near else ("ntc_melt_other", "warning")
                flags.append(Flag(severity, code, {"tm": tm}, run_id, (well.coord,), target, well.sample))
            continue
        if len(result.tms) > 1:
            flags.append(Flag("warning", "melt_multiple_peaks", {"count": len(result.tms)}, run_id, (well.coord,), target, well.sample))
        if result.tms and median is not None and abs(result.tms[0] - median) > s.tm_shift_max:
            flags.append(Flag("warning", "melt_tm_shift", {"tm": result.tms[0], "median": median}, run_id, (well.coord,), target, well.sample))
    return flags


def _disagreement_flags(s: Settings, run_id: str, target: str, rows: list[tuple[Well, Reaction, CurveResult]]) -> list[Flag]:
    """A constant shift only means another threshold; a reaction apart from the others means trouble."""
    pairs = [(w, r.cq - c.cq_calc) for w, r, c in rows if r.cq is not None and c.cq_calc is not None and r.role != "ntc"]
    if len(pairs) < 3:
        return []
    median = float(np.median([d for _, d in pairs]))
    return [
        Flag("warning", "cq_source_disagree", {"delta": d - median, "limit": s.cq_disagree_max}, run_id, (w.coord,), target, w.sample)
        for w, d in pairs
        if abs(d - median) > s.cq_disagree_max
    ]

"""Synthetic curves with known Cq, efficiency and Tm."""

from __future__ import annotations

import numpy as np

from qpcr_core.models import Curve

_LINEAR_UP_TO = 0.2  # of the plateau: strictly exponential below, smooth saturation above


def logistic(
    cq_at_t: float,
    efficiency: float = 0.95,
    plateau: float = 2.0,
    threshold: float = 0.1,
    cycles: int = 40,
    background: float = 0.5,
    drift: float = 0.0,
    noise: float = 0.0,
    seed: int = 0,
    subtracted: bool = False,
) -> Curve:
    """A curve crossing ``threshold`` at ``cq_at_t``; ``subtracted`` keeps ``background`` as a residual offset, no drift."""
    x = np.arange(1, cycles + 1, dtype=float)
    pure = threshold * (1 + efficiency) ** (x - cq_at_t)
    knee = _LINEAR_UP_TO * plateau
    span = plateau - knee
    y = np.where(pure <= knee, pure, knee + span * (1 - np.exp(-(pure - knee) / span)))
    y = y + background + (0.0 if subtracted else drift * x)
    if noise:
        y = y + np.random.default_rng(seed).normal(0, noise, cycles)
    return Curve(x.tolist(), y.tolist())


def flat(level: float = 0.5, drift: float = 0.0, noise: float = 0.0, cycles: int = 40, seed: int = 0) -> Curve:
    x = np.arange(1, cycles + 1, dtype=float)
    y = level + drift * x
    if noise:
        y = y + np.random.default_rng(seed).normal(0, noise, cycles)
    return Curve(x.tolist(), y.tolist())


def melt(
    tm: float = 84.0,
    step: float = 0.5,
    height: float = 1.0,
    noise: float = 0.0,
    second_tm: float | None = None,
    second_height: float = 0.0,
    seed: int = 0,
    start: float = 65.0,
    stop: float = 95.0,
    quenching: float = 0.02,
) -> Curve:
    """A melt: logistic falls whose -dF/dT peaks have the given heights, over thermal quenching."""
    x = np.arange(start, stop + step / 2, step)

    def fall(t: float, h: float) -> np.ndarray:
        return 4 * h / (1 + np.exp(x - t))

    y = fall(tm, height) + 5.0 - quenching * (x - start)
    if second_tm is not None:
        y = y + fall(second_tm, second_height)
    if noise:
        y = y + np.random.default_rng(seed).normal(0, noise, x.size)
    return Curve(x.tolist(), y.tolist())

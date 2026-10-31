"""Group statistics on the log2(RQ) scale: summaries, Welch / ANOVA + Dunnett or Tukey, BH."""

from __future__ import annotations

import inspect
import math
from collections import defaultdict
from dataclasses import dataclass
from statistics import fmean, stdev

import numpy as np
from scipy import stats as sps

from .flags import Flag
from .relquant import SampleRQ


@dataclass
class GroupSummary:
    target: str
    group: str
    n: int
    mean_log2: float
    sd_log2: float | None
    sem_log2: float | None
    ci95_log2: float | None  # half-width

    @property
    def fold(self) -> float:
        return 2**self.mean_log2

    def fold_bounds(self, kind: str) -> tuple[float, float]:
        err = {"sd": self.sd_log2, "sem": self.sem_log2, "ci95": self.ci95_log2}[kind]
        if err is None:
            return self.fold, self.fold
        return 2 ** (self.mean_log2 - err), 2 ** (self.mean_log2 + err)


@dataclass
class Comparison:
    target: str
    group_a: str
    group_b: str
    test: str  # welch | anova | dunnett | tukey ; anova uses "*" for both groups
    statistic: float
    p: float
    p_adj: float | None = None


def bh_adjust(pvalues: list[float]) -> list[float]:
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted = [0.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, pvalues[i] * m / rank)
        adjusted[i] = running
    return adjusted


def _by_target_group(rqs: list[SampleRQ]) -> dict[str, dict[str, list[float]]]:
    out: dict[str, dict[str, list[float]]] = defaultdict(dict)
    for r in rqs:
        out[r.target].setdefault(r.group, []).append(r.log2_rq)
    return out


def summarize(rqs: list[SampleRQ]) -> list[GroupSummary]:
    out: list[GroupSummary] = []
    for target, groups in _by_target_group(rqs).items():
        for group, v in groups.items():
            n = len(v)
            sd = stdev(v) if n > 1 else None
            sem = sd / math.sqrt(n) if sd is not None else None
            ci = float(sps.t.ppf(0.975, n - 1)) * sem if sem is not None else None
            out.append(GroupSummary(target, group, n, fmean(v), sd, sem, ci))
    return out


def _dunnett(others: list[list[float]], control: list[float]):
    kw = {"rng": np.random.default_rng(0)} if "rng" in inspect.signature(sps.dunnett).parameters else {"random_state": 0}
    return sps.dunnett(*others, control=control, **kw)


def compare(rqs: list[SampleRQ], control_group: str, test: str) -> tuple[list[Comparison], list[Flag]]:
    comps: list[Comparison] = []
    flags: list[Flag] = []
    for target, groups in _by_target_group(rqs).items():
        names = sorted(groups, key=lambda g: g != control_group)  # control first, then data order
        eligible = []
        for g in names:
            if len(groups[g]) < 2:
                flags.append(Flag("info", "too_few_bio_reps", {"group": g}, target=target))
            else:
                eligible.append(g)
        if len(eligible) < 2:
            continue
        data = [groups[g] for g in eligible]
        if len(eligible) == 2:
            res = sps.ttest_ind(data[0], data[1], equal_var=False)
            comps.append(Comparison(target, eligible[0], eligible[1], "welch", float(res.statistic), float(res.pvalue)))
            continue
        res = sps.f_oneway(*data)
        comps.append(Comparison(target, "*", "*", "anova", float(res.statistic), float(res.pvalue)))
        if test == "dunnett" and control_group in eligible:
            res = _dunnett(data[1:], data[0])
            for g, st, p in zip(eligible[1:], res.statistic, res.pvalue):
                comps.append(Comparison(target, control_group, g, "dunnett", float(st), float(p)))
        else:
            res = sps.tukey_hsd(*data)
            for i in range(len(eligible)):
                for j in range(i + 1, len(eligible)):
                    comps.append(
                        Comparison(target, eligible[i], eligible[j], "tukey", float(res.statistic[i, j]), float(res.pvalue[i, j]))
                    )

    families: dict[tuple[str, str, str], list[Comparison]] = defaultdict(list)
    for c in comps:
        families[(c.group_a, c.group_b, c.test)].append(c)
    for fam in families.values():
        for c, adj in zip(fam, bh_adjust([c.p for c in fam])):
            c.p_adj = adj
    return comps, flags

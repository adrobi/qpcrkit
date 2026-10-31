import math

import numpy as np
import pytest

from qpcr_core.stdcurve import fit_std_curves, quantify
from tests.factories import make_project


def raw_cq(run, rxn):
    return None if rxn.excluded else rxn.cq


def _ideal_rows(run="R1", target="IL6"):
    rows, i = [], 0
    for q in (1e5, 1e4, 1e3, 1e2):
        for _ in range(2):
            i += 1
            rows.append((run, f"A{i}", None, target, "std", 40 - math.log2(q), q))
    rows.append((run, "B1", None, target, "std", 40 - math.log2(10), 10.0))
    rows.append((run, "B2", None, target, "std", None, 10.0))
    return rows


def test_ideal_curve():
    curves, flags = fit_std_curves(make_project(_ideal_rows()), raw_cq)
    c = curves[(None, "IL6")]
    assert c.slope == pytest.approx(-1 / math.log10(2), abs=1e-6)
    assert c.intercept == pytest.approx(40.0, abs=1e-6)
    assert c.r2 == pytest.approx(1.0, abs=1e-9)
    assert c.efficiency == pytest.approx(1.0, abs=1e-6)
    assert (c.n_points, c.n_levels) == (9, 5)
    assert c.lowest_detected == 100.0
    assert (c.min_q, c.max_q) == (10.0, 1e5)
    assert flags == []


def test_quantify():
    c = fit_std_curves(make_project(_ideal_rows()), raw_cq)[0][(None, "IL6")]
    q, extra = quantify(c, 30.0)
    assert q == pytest.approx(1024.0) and extra is False
    q, extra = quantify(c, 38.0)
    assert q == pytest.approx(4.0) and extra is True


def test_noisy_matches_numpy():
    qs = [1e5, 1e4, 1e3, 1e2]
    cqs = [23.1, 26.3, 29.9, 33.0]
    p = make_project([("R1", f"A{i}", None, "IL6", "std", cq, q) for i, (q, cq) in enumerate(zip(qs, cqs))])
    c = fit_std_curves(p, raw_cq)[0][(None, "IL6")]
    m, b = np.polyfit(np.log10(qs), cqs, 1)
    assert c.slope == pytest.approx(m) and c.intercept == pytest.approx(b)
    assert c.r2 == pytest.approx(np.corrcoef(np.log10(qs), cqs)[0, 1] ** 2)


def test_two_levels_no_curve():
    p = make_project([("R1", "A1", None, "IL6", "std", 20.0, 100.0), ("R1", "A2", None, "IL6", "std", 23.3, 10.0)])
    curves, flags = fit_std_curves(p, raw_cq)
    assert curves == {}
    assert [(f.code, f.severity, f.target, f.params) for f in flags] == [("std_levels_few", "warning", "IL6", {"levels": 2})]


def test_efficiency_out_of_range():
    p = make_project([("R1", f"A{i}", None, "IL6", "std", 40 - 3.0 * math.log10(q), q) for i, q in enumerate((1e4, 1e3, 1e2))])
    curves, flags = fit_std_curves(p, raw_cq)
    assert curves[(None, "IL6")].efficiency == pytest.approx(10 ** (1 / 3) - 1)
    assert [f.code for f in flags] == ["efficiency_out_of_range"]


def test_low_r2():
    cqs = [20.0, 24.5, 26.0, 31.5]
    p = make_project([("R1", f"A{i}", None, "IL6", "std", cq, q) for i, (q, cq) in enumerate(zip((1e5, 1e4, 1e3, 1e2), cqs))])
    curves, flags = fit_std_curves(p, raw_cq)
    assert curves[(None, "IL6")].r2 < 0.98
    assert "r2_low" in [f.code for f in flags]


def test_zero_or_missing_quantity_ignored():
    rows = _ideal_rows() + [("R1", "C1", None, "IL6", "std", 30.0, 0.0), ("R1", "C2", None, "IL6", "std", 30.0, None)]
    c = fit_std_curves(make_project(rows), raw_cq)[0][(None, "IL6")]
    assert c.n_points == 9


def test_per_run_curves():
    p = make_project(_ideal_rows("R1") + _ideal_rows("R2"), pool_std_runs=False)
    curves, _ = fit_std_curves(p, raw_cq)
    assert set(curves) == {("R1", "IL6"), ("R2", "IL6")}


def test_standard_without_quantity_flagged():
    rows = _ideal_rows() + [("R1", "C2", None, "IL6", "std", 30.0, None)]
    _, flags = fit_std_curves(make_project(rows), raw_cq)
    assert [(f.code, f.severity, f.target, f.coords) for f in flags] == [("std_no_quantity", "warning", "IL6", ("C2",))]

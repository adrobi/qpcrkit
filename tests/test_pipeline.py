import math

import pytest

from qpcr_core.pipeline import analyze
from qpcr_core.sessions import project_to_dict
from tests.factories import make_project

IL6 = {"c": [28.0, 28.2, 27.9], "l": [25.0, 25.1, 24.8], "d": [27.0, 26.9, 27.2]}
GROUPS = {"c": "Ctrl", "l": "LPS", "d": "Dex"}


def demo_rows():
    rows = []
    for run, shift in (("R1", 0.0), ("R2", 0.4)):
        rows += [
            (run, "H1", "irc", "GAPDH", "irc", 20.0 + shift, None),
            (run, "H2", "irc", "GAPDH", "irc", 20.0 + shift, None),
            (run, "H3", "irc", "IL6", "irc", 25.0 + shift, None),
            (run, "H4", "irc", "IL6", "irc", 25.0 + shift, None),
        ]
    for i, q in enumerate((1e5, 1e4, 1e3, 1e2)):
        rows.append(("R1", f"G{i + 1}", None, "IL6", "std", 40 - math.log2(q), q))
    col = 0
    for key, run, shift in (("c", "R1", 0.0), ("l", "R2", 0.4), ("d", "R2", 0.4)):
        for i, il6 in enumerate(IL6[key]):
            sample = f"{key}{i + 1}"
            for rep in range(2):
                col += 1
                rows.append((run, f"A{col}", sample, "GAPDH", "unknown", 20.0 + shift + 0.05 * rep, None))
                col += 1
                rows.append((run, f"A{col}", sample, "IL6", "unknown", il6 + shift + 0.05 * rep, None))
    return rows


def demo_project():
    groups = {f"{k}{i + 1}": g for k, g in GROUPS.items() for i in range(3)}
    return make_project(demo_rows(), groups=groups, refs=("GAPDH",), control_group="Ctrl")


def test_end_to_end():
    res = analyze(demo_project())
    assert res.calibration[("R2", "GAPDH")] == pytest.approx(0.2)
    assert res.mean_cq[("l1", "GAPDH")] == pytest.approx(20.225)  # raw 20.4/20.45 minus CF 0.2
    assert res.efficiencies["IL6"] == pytest.approx(1.0, abs=1e-6)
    assert {g.group for g in res.groups if g.target == "IL6"} == {"Ctrl", "LPS", "Dex"}
    lps = next(g for g in res.groups if (g.target, g.group) == ("IL6", "LPS"))
    assert lps.fold == pytest.approx(2 ** (28.0333333 - 24.9666667), rel=1e-4)
    assert {c.test for c in res.comparisons} == {"anova", "dunnett"}
    assert res.quantities and all(q.target == "IL6" for q in res.quantities)
    assert res.flags_by_severity("error") == []


def test_excluding_outlier_changes_results():
    rows = [r for r in demo_rows()] + [("R1", "P1", "c1", "IL6", "unknown", 30.0, None)]
    groups = {f"{k}{i + 1}": g for k, g in GROUPS.items() for i in range(3)}
    p = make_project(rows, groups=groups, refs=("GAPDH",), control_group="Ctrl")
    before = analyze(p)
    assert any(f.code == "rep_sd_high" and f.sample == "c1" for f in before.flags)
    p.run("R1").wells["P1"].reactions[0].excluded = True
    after = analyze(p)
    assert not any(f.code == "rep_sd_high" and f.sample == "c1" for f in after.flags)
    assert after.mean_cq[("c1", "IL6")] < before.mean_cq[("c1", "IL6")]


def test_excluded_irc_and_standard_ignored():
    p = demo_project()
    p.run("R2").wells["H1"].reactions[0].cq = 99.0
    p.run("R2").wells["H1"].reactions[0].excluded = True
    p.run("R1").wells["G1"].reactions[0].excluded = True
    res = analyze(p)
    assert res.calibration[("R2", "GAPDH")] == pytest.approx(0.2)
    assert len(res.std_curves[(None, "IL6")].points) == 3


def test_no_standards_no_irc():
    rows = [r for r in demo_rows() if r[4] not in ("irc", "std") and r[0] == "R1"] + [
        ("R1", f"B{i}", f"x{i}", t, "unknown", cq, None)
        for i in range(1, 3)
        for t, cq in (("GAPDH", 20.0), ("IL6", 26.0))
    ]
    groups = {"c1": "Ctrl", "c2": "Ctrl", "c3": "Ctrl", "x1": "X", "x2": "X"}
    res = analyze(make_project(rows, groups=groups, refs=("GAPDH",), control_group="Ctrl"))
    assert res.std_curves == {}
    assert res.efficiencies == {"GAPDH": 1.0, "IL6": 1.0}
    assert res.rqs


def test_analyze_does_not_mutate():
    p = demo_project()
    snapshot = project_to_dict(p)
    analyze(p)
    assert project_to_dict(p) == snapshot

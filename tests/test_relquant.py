import math

import pytest

from qpcr_core.models import Project, Sample, Settings, Target
from qpcr_core.relquant import efficiencies, relative_quantities
from qpcr_core.stdcurve import StdCurve

MEAN = {
    ("c1", "IL6"): 25.0, ("c1", "GAPDH"): 20.0,
    ("c2", "IL6"): 25.4, ("c2", "GAPDH"): 20.2,
    ("s1", "IL6"): 23.2, ("s1", "GAPDH"): 20.1,
}


def _project(refs=("GAPDH",), control="Ctrl", calibrator="", targets=("IL6", "GAPDH")):
    p = Project(settings=Settings(control_group=control, calibrator_sample=calibrator))
    for t in targets:
        p.targets[t] = Target(t, kind="reference" if t in refs else "target")
    for name, g in (("c1", "Ctrl"), ("c2", "Ctrl"), ("s1", "LPS")):
        p.samples[name] = Sample(name, group=g)
    return p


def _rq(rqs, sample, target="IL6"):
    return next(r for r in rqs if r.sample == sample and r.target == target)


def test_pfaffl():
    rqs, flags = relative_quantities(_project(), MEAN, {"IL6": 0.9, "GAPDH": 1.0})
    r = _rq(rqs, "s1")
    assert r.delta_cq == pytest.approx(2.0)
    assert r.rq == pytest.approx(3.61)
    assert r.log2_rq == pytest.approx(math.log2(3.61))
    assert r.group == "LPS" and r.mean_cq == 23.2
    assert flags == []
    assert {x.target for x in rqs} == {"IL6"}


def test_ddct_special_case():
    rqs, _ = relative_quantities(_project(), MEAN, {"IL6": 1.0, "GAPDH": 1.0})
    assert _rq(rqs, "s1").rq == pytest.approx(4.0)


def test_two_references_geomean():
    mean = dict(MEAN)
    # REF2: calibrator 20.0 ; s1 21.0 -> dCq -1 ; GAPDH s1 -> dCq +1 (calibrator 20.1 → s1 19.1)
    mean.update({("c1", "REF2"): 20.0, ("c2", "REF2"): 20.0, ("s1", "REF2"): 21.0, ("s1", "GAPDH"): 19.1})
    p = _project(refs=("GAPDH", "REF2"), targets=("IL6", "GAPDH", "REF2"))
    rqs, _ = relative_quantities(p, mean, {"IL6": 1.0, "GAPDH": 1.0, "REF2": 1.0})
    assert _rq(rqs, "s1").rq == pytest.approx(4.0)


def test_calibrator_sample():
    rqs, _ = relative_quantities(_project(control="", calibrator="c1"), MEAN, {"IL6": 1.0, "GAPDH": 1.0})
    assert _rq(rqs, "s1").delta_cq == pytest.approx(1.8)


def test_no_control():
    rqs, flags = relative_quantities(_project(control=""), MEAN, {})
    assert rqs == [] and [(f.severity, f.code) for f in flags] == [("error", "no_control")]


def test_no_reference_targets():
    rqs, flags = relative_quantities(_project(refs=()), MEAN, {})
    assert rqs == [] and [(f.severity, f.code) for f in flags] == [("error", "no_reference_targets")]


def test_sample_without_reference():
    mean = dict(MEAN)
    mean[("s1", "GAPDH")] = None
    rqs, flags = relative_quantities(_project(), mean, {"IL6": 1.0, "GAPDH": 1.0})
    assert [(f.code, f.sample) for f in flags] == [("no_reference_for_sample", "s1")]
    assert flags[0].severity == "error"
    assert {r.sample for r in rqs} == {"c1", "c2"}


def test_missing_target_cq():
    mean = dict(MEAN)
    mean[("s1", "IL6")] = None
    mean.update({("c1", "TNF"): 30.0, ("c2", "TNF"): 30.0, ("s1", "TNF"): 28.0})
    p = _project(targets=("IL6", "GAPDH", "TNF"))
    rqs, flags = relative_quantities(p, mean, {"IL6": 1.0, "GAPDH": 1.0, "TNF": 1.0})
    assert [(f.severity, f.code, f.sample, f.target) for f in flags] == [("info", "no_cq", "s1", "IL6")]
    assert _rq(rqs, "s1", "TNF").rq == pytest.approx(2 ** 2.0 / 2 ** 0.0)


def test_no_calibrator_cq_for_target():
    mean = dict(MEAN)
    mean.update({("c1", "TNF"): None, ("c2", "TNF"): None, ("s1", "TNF"): 28.0})
    p = _project(targets=("IL6", "GAPDH", "TNF"))
    rqs, flags = relative_quantities(p, mean, {"IL6": 1.0, "GAPDH": 1.0, "TNF": 1.0})
    assert [(f.severity, f.code, f.target) for f in flags] == [("error", "no_calibrator_cq", "TNF")]
    assert _rq(rqs, "s1", "IL6").rq == pytest.approx(4.0)


def _curve(eff):
    return StdCurve("IL6", None, -3.3, 40, 1.0, eff, 4, 4, 10, 1e4, 10, [])


def test_efficiencies_modes():
    p = _project()
    p.targets["GAPDH"].efficiency_mode = "manual"
    p.targets["GAPDH"].efficiency_manual = 0.97
    assert efficiencies(p, {(None, "IL6"): _curve(0.92)}) == {"IL6": 0.92, "GAPDH": 0.97}
    p.targets["IL6"].efficiency_manual = 0.95
    assert efficiencies(p, {})["IL6"] == 0.95
    p.targets["IL6"].efficiency_manual = None
    assert efficiencies(p, {})["IL6"] == 1.0
    p.targets["IL6"].efficiency_mode = "ideal"
    assert efficiencies(p, {(None, "IL6"): _curve(0.92)})["IL6"] == 1.0
    p.targets["IL6"].efficiency_mode = "stdcurve"
    curves = {("R1", "IL6"): _curve(0.90), ("R2", "IL6"): _curve(0.94)}
    assert efficiencies(p, curves)["IL6"] == pytest.approx(0.92)


def _two_ref_project():
    return _project(refs=("GAPDH", "REF2"), targets=("IL6", "GAPDH", "REF2"))


def test_partial_reference_flagged():
    mean = dict(MEAN)
    mean.update({("c1", "REF2"): 20.0, ("c2", "REF2"): 20.0, ("s1", "REF2"): None})
    rqs, flags = relative_quantities(_two_ref_project(), mean, {"IL6": 1.0, "GAPDH": 1.0, "REF2": 1.0})
    assert [(f.severity, f.code, f.sample) for f in flags] == [("warning", "partial_reference", "s1")]
    assert _rq(rqs, "s1").rq == pytest.approx(4.0)


def test_reference_without_calibrator_cq():
    mean = dict(MEAN)
    mean.update({("c1", "REF2"): None, ("c2", "REF2"): None, ("s1", "REF2"): 21.0})
    _, flags = relative_quantities(_two_ref_project(), mean, {"IL6": 1.0, "GAPDH": 1.0, "REF2": 1.0})
    assert [(f.severity, f.code, f.target) for f in flags] == [("error", "no_calibrator_cq", "REF2")]


def test_samples_without_group():
    p = _project()
    p.samples["x"] = Sample("x")
    mean = dict(MEAN)
    mean.update({("x", "IL6"): 22.0, ("x", "GAPDH"): 20.0})
    _, flags = relative_quantities(p, mean, {"IL6": 1.0, "GAPDH": 1.0})
    assert [(f.severity, f.code, f.params) for f in flags] == [("warning", "samples_without_group", {"count": 1})]


def test_efficiency_sources_and_unusable_curve():
    from qpcr_core.relquant import efficiencies_with_source

    p = _project()
    p.targets["GAPDH"].efficiency_mode = "manual"
    p.targets["GAPDH"].efficiency_manual = 0.97
    eff, source, flags = efficiencies_with_source(p, {(None, "IL6"): _curve(-1.0)})
    assert eff == {"IL6": 1.0, "GAPDH": 0.97}
    assert source == {"IL6": "ideal", "GAPDH": "manual"}
    assert [(f.code, f.target) for f in flags] == [("efficiency_unusable", "IL6")]
    eff, source, flags = efficiencies_with_source(p, {(None, "IL6"): _curve(0.93)})
    assert (eff["IL6"], source["IL6"], flags) == (0.93, "stdcurve", [])

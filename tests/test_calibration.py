import pytest

from qpcr_core.calibration import calibration_factors, corrected_cq
from tests.factories import make_project

BASE = [
    ("R1", "A1", "irc", "GAPDH", "irc", 20.0, None),
    ("R1", "A2", "irc", "GAPDH", "irc", 20.2, None),
    ("R1", "B1", "s1", "IL6", "unknown", 25.0, None),
    ("R2", "A1", "irc", "GAPDH", "irc", 21.0, None),
    ("R2", "A2", "irc", "GAPDH", "irc", 21.2, None),
    ("R2", "B1", "s2", "IL6", "unknown", 26.0, None),
]


def test_per_target_factors():
    cf, flags = calibration_factors(make_project(BASE))
    assert cf[("R1", "GAPDH")] == pytest.approx(-0.5)
    assert cf[("R2", "GAPDH")] == pytest.approx(0.5)
    assert flags == []


def test_fallback_uses_all_irc():
    cf, _ = calibration_factors(make_project(BASE))
    assert cf[("R1", "IL6")] == pytest.approx(-0.5)
    assert cf[("R2", "IL6")] == pytest.approx(0.5)


def test_run_without_irc():
    p = make_project(BASE + [("R3", "B1", "s3", "IL6", "unknown", 24.0, None)])
    cf, flags = calibration_factors(p)
    assert [(f.code, f.severity, f.run_id) for f in flags] == [("irc_missing", "warning", "R3")]
    assert cf.get(("R3", "GAPDH"), 0.0) == 0.0
    assert cf.get(("R3", "IL6"), 0.0) == 0.0
    assert cf[("R1", "GAPDH")] == pytest.approx(-0.5)
    assert cf[("R2", "IL6")] == pytest.approx(0.5)


def test_single_run():
    assert calibration_factors(make_project(BASE[:3])) == ({}, [])


def test_no_irc_at_all():
    p = make_project([("R1", "B1", "s1", "IL6", "unknown", 25.0, None), ("R2", "B1", "s2", "IL6", "unknown", 26.0, None)])
    cf, flags = calibration_factors(p)
    assert cf == {}
    assert [(f.code, f.severity) for f in flags] == [("no_irc", "info")]


def test_excluded_irc_ignored():
    p = make_project(BASE)
    p.run("R2").wells["A2"].reactions[0].excluded = True  # R2 mean becomes 21.0
    cf, _ = calibration_factors(p)
    assert cf[("R2", "GAPDH")] == pytest.approx(0.45)


def test_corrected_cq():
    cf, _ = calibration_factors(make_project(BASE))
    assert corrected_cq(cf, "R2", "GAPDH", 25.0) == pytest.approx(24.5)
    assert corrected_cq(cf, "R9", "X", 25.0) == 25.0

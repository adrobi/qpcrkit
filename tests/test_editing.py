import pytest

from qpcr_core import editing as ed
from qpcr_core.sessions import project_to_dict
from tests.factories import make_project


def _p():
    return make_project([
        ("R1", "A1", None, "GAPDH", "unknown", 20.0, None),
        ("R1", "A1", None, "IL6", "unknown", 25.0, None),
        ("R1", "A2", None, "GAPDH", "unknown", 20.1, None),
    ])


def test_assign_sample():
    p = _p()
    ed.assign_sample(p, "R1", ["A1", "A2"], "s1")
    assert p.run("R1").wells["A2"].sample == "s1" and "s1" in p.samples
    ed.assign_sample(p, "R1", ["A2"], "")
    assert p.run("R1").wells["A2"].sample is None


def test_set_role_for_one_target():
    p = _p()
    ed.set_role(p, "R1", ["A1"], "std", target="IL6")
    gapdh, il6 = p.run("R1").wells["A1"].reactions
    assert (gapdh.role, il6.role) == ("unknown", "std")
    ed.set_role(p, "R1", ["A1"], "ntc")
    assert {r.role for r in p.run("R1").wells["A1"].reactions} == {"ntc"}


def test_set_quantity():
    p = _p()
    ed.set_quantity(p, "R1", ["A1"], 100.0, target="IL6")
    assert p.run("R1").wells["A1"].reactions[1].quantity == 100.0
    assert p.run("R1").wells["A1"].reactions[0].quantity is None


def test_set_group_and_kind_and_settings():
    p = _p()
    ed.set_group(p, "s9", "LPS")
    assert p.samples["s9"].group == "LPS"
    ed.set_target_kind(p, "GAPDH", "reference")
    assert p.targets["GAPDH"].kind == "reference"
    ed.update_settings(p, control_group="Ctrl", rep_sd_max=0.5)
    assert (p.settings.control_group, p.settings.rep_sd_max) == ("Ctrl", 0.5)
    with pytest.raises(AttributeError):
        ed.update_settings(p, nope=1)


def test_set_excluded():
    p = _p()
    ed.set_excluded(p, "R1", "A1", "IL6", True, "bubble")
    gapdh, il6 = p.run("R1").wells["A1"].reactions
    assert il6.excluded and il6.exclude_reason == "bubble" and not gapdh.excluded
    ed.set_excluded(p, "R1", "A1", None, True)
    assert gapdh.excluded
    with pytest.raises(KeyError):
        ed.set_excluded(p, "R1", "Z9", None, True)


def test_apply_sample_table():
    p = _p()
    n = ed.apply_sample_table(p, [["s1", "LPS", "1"], ["s2", "Ctrl"], [""], []])
    assert n == 2
    assert p.samples["s1"].group == "LPS" and p.samples["s1"].bio_replicate == "1"
    assert p.samples["s2"].group == "Ctrl"


def test_history_undo_redo():
    p = _p()
    h = ed.EditHistory()
    before = project_to_dict(p)
    h.record(p)
    ed.set_group(p, "s1", "LPS")
    after = project_to_dict(p)
    undone = h.undo(p)
    assert project_to_dict(undone) == before and h.can_redo
    redone = h.redo(undone)
    assert project_to_dict(redone) == after
    assert not h.can_redo


def test_record_clears_redo_and_depth():
    p = _p()
    h = ed.EditHistory(max_depth=3)
    h.record(p)
    p = h.undo(p)
    assert h.can_redo
    h.record(p)
    assert not h.can_redo
    for _ in range(10):
        h.record(p)
    n = 0
    while h.can_undo:
        p = h.undo(p)
        n += 1
    assert n == 3
    assert h.undo(p) is None

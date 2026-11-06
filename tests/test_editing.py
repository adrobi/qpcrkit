import pytest

from qpcr_core import editing as ed
from qpcr_core.sessions import project_to_dict
from qpcr_core.editing import EditHistory, rename_target_in_run, set_target
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


def test_curves_are_shared_in_undo_snapshots():
    from qpcr_core.editing import clone_project
    from qpcr_core.models import Curve

    p = _p()
    curve = Curve([1, 2], [3, 4])
    p.run("R1").wells["A1"].reactions[0].amplification = curve
    snap = clone_project(p)
    assert snap == p
    assert snap.run("R1").wells["A1"].reactions[0].amplification is curve
    ed.set_excluded(p, "R1", "A1", None, True)
    ed.set_group(p, "s1", "LPS")
    assert not snap.run("R1").wells["A1"].reactions[0].excluded
    assert "s1" not in snap.samples


def _sybr():
    p = make_project([
        ("R1", "A1", None, "SYBR", "unknown", 20.0, None),
        ("R1", "A2", None, "SYBR", "unknown", 21.0, None),
        ("R2", "A1", None, "SYBR", "unknown", 22.0, None),
    ])
    for _, _, r in p.iter_reactions():
        r.fluor = "SYBR"
    return p


def test_unassigned_targets():
    p = _sybr()
    assert p.unassigned_targets() == [("R1", "A1"), ("R1", "A2"), ("R2", "A1")]
    ed.set_target(p, "R1", ["A1"], "GAPDH")
    assert ("R1", "A1") not in p.unassigned_targets()


def test_set_target_prunes_only_unused():
    p = _sybr()
    ed.set_target(p, "R1", ["A1", "A2"], "GAPDH")
    assert "GAPDH" in p.targets and "SYBR" in p.targets  # R2 still uses it
    ed.set_target(p, "R2", ["A1"], "GAPDH")
    assert "SYBR" not in p.targets


def test_set_target_with_fluor_touches_one_reaction():
    p = _p()
    p.run("R1").wells["A1"].reactions[0].fluor = "FAM"
    p.run("R1").wells["A1"].reactions[1].fluor = "VIC"
    ed.set_target(p, "R1", ["A1"], "X", fluor="VIC")
    assert [r.target for r in p.run("R1").wells["A1"].reactions] == ["GAPDH", "X"]


def test_rename_keeps_settings():
    p = _sybr()
    p.targets["SYBR"].efficiency_manual = 0.95
    ed.rename_target_in_run(p, "R1", "SYBR", "GAPDH")
    assert p.targets["GAPDH"].efficiency_manual == 0.95
    assert p.run("R2").wells["A1"].reactions[0].target == "SYBR"


def test_rename_into_existing_merges_and_keeps_reference():
    p = _sybr()
    ed.set_target(p, "R2", ["A1"], "GAPDH")
    p.targets["SYBR"].kind = "reference"
    ed.rename_target_in_run(p, "R1", "SYBR", "GAPDH")
    assert p.targets["GAPDH"].kind == "reference"
    assert "SYBR" not in p.targets
    assert {r.target for _, _, r in p.iter_reactions()} == {"GAPDH"}


def test_fill_series():
    p = make_project([("R1", f"A{i}", None, "IL6", "unknown", 20.0, None) for i in range(1, 7)])
    ed.fill_series(p, "R1", [f"A{i}" for i in range(1, 7)], "Ctrl-", replicates=3)
    wells = p.run("R1").wells
    assert [wells[f"A{i}"].sample for i in range(1, 7)] == ["Ctrl-1"] * 3 + ["Ctrl-2"] * 3
    ed.fill_series(p, "R1", ["A1", "A2"], "S", start=5)
    assert wells["A2"].sample == "S6"


def test_apply_plate_map():
    p = make_project([("R1", "A1", "old", "IL6", "unknown", 20.0, None), ("R1", "B2", None, "IL6", "unknown", 20.0, None)])
    rows = [["", "x"] + [""] * 20, ["", "s2", "extra"]] + [["z"]] * 20
    assert ed.apply_plate_map(p, "R1", rows) == 1  # only B2 exists and is filled; A1 keeps its sample
    assert p.run("R1").wells["B2"].sample == "s2"
    assert p.run("R1").wells["A1"].sample == "old"


def test_plate_map_with_headers():
    p = make_project([("R1", "B2", None, "IL6", "unknown", 20.0, None)])
    rows = [[""] + [str(i) for i in range(1, 13)], ["A"] + [""] * 12, ["B", "", "s2"]]
    assert ed.apply_plate_map(p, "R1", rows) == 1
    assert p.run("R1").wells["B2"].sample == "s2"


def test_plate_map_ignored_on_rotor():
    p = make_project([("R1", "1", None, "IL6", "unknown", 20.0, None)])
    p.runs[0].plate_format = 72
    assert ed.apply_plate_map(p, "R1", [["s"]]) == 0


def test_samples_with_a_group_survive_pruning():
    p = _sybr()
    ed.apply_sample_table(p, [["later", "LPS"]])
    p.prune_orphans()
    assert p.samples["later"].group == "LPS"


def test_orphan_cleanup_undone_by_history():
    p = _sybr()
    h = ed.EditHistory()
    h.record(p)
    ed.set_target(p, "R1", ["A1", "A2"], "G")
    ed.set_target(p, "R2", ["A1"], "G")
    assert "SYBR" not in p.targets
    assert "SYBR" in h.undo(p).targets


def test_rename_into_default_target_carries_settings():
    p = _sybr()
    ed.set_target(p, "R2", ["A1"], "GAPDH")
    ed.set_target(p, "R1", ["A1"], "SYBR")
    p.targets["SYBR"].efficiency_mode = "manual"
    p.targets["SYBR"].efficiency_manual = 0.92
    ed.rename_target_in_run(p, "R1", "SYBR", "GAPDH")
    assert (p.targets["GAPDH"].efficiency_mode, p.targets["GAPDH"].efficiency_manual) == ("manual", 0.92)


def test_prune_keeps_annotated_samples_and_calibrator():
    p = _sybr()
    ed.apply_sample_table(p, [["rep", "", "2"]])
    p.samples["cal"] = ed.Sample("cal")
    p.settings.calibrator_sample = "cal"
    p.samples["junk"] = ed.Sample("junk")
    p.prune_orphans()
    assert {"rep", "cal"} <= set(p.samples) and "junk" not in p.samples


def test_assign_sample_drops_the_old_name():
    p = _p()
    ed.assign_sample(p, "R1", ["A1", "A2"], "old")
    ed.assign_sample(p, "R1", ["A1", "A2"], "new")
    assert "old" not in p.samples and "new" in p.samples


# --- manual thresholds follow the target ---


def _with_threshold():
    p = make_project(
        [("R1", "A1", "s", "SYBR", "unknown", 20.0, None), ("R1", "A2", "s", "SYBR", "unknown", 20.0, None)]
    )
    p.runs[0].thresholds["SYBR"] = 0.2
    return p


def test_undo_restores_a_manual_threshold():
    p = _with_threshold()
    history = EditHistory()
    history.record(p)
    p.runs[0].thresholds["SYBR"] = 0.5
    assert history.undo(p).runs[0].thresholds["SYBR"] == 0.2


def test_rename_takes_the_threshold_along():
    p = _with_threshold()
    rename_target_in_run(p, "R1", "SYBR", "GAPDH")
    assert p.runs[0].thresholds == {"GAPDH": 0.2}


def test_rename_keeps_the_threshold_already_set_on_the_new_name():
    p = _with_threshold()
    p.runs[0].thresholds["GAPDH"] = 0.3
    rename_target_in_run(p, "R1", "SYBR", "GAPDH")
    assert p.runs[0].thresholds == {"GAPDH": 0.3}


def test_threshold_of_a_target_gone_from_the_run_is_dropped():
    p = _with_threshold()
    set_target(p, "R1", ["A1", "A2"], "GAPDH")
    assert p.runs[0].thresholds == {}


def test_threshold_stays_while_some_wells_keep_the_target():
    p = _with_threshold()
    set_target(p, "R1", ["A1"], "GAPDH")
    assert p.runs[0].thresholds == {"SYBR": 0.2}


# --- manual threshold ---


def test_set_threshold_sets_and_removes():
    p = make_project([("R1", "A1", "s", "T", "unknown", 20.0, None)])
    ed.set_threshold(p, "R1", "T", 0.2)
    assert p.runs[0].thresholds == {"T": 0.2}
    ed.set_threshold(p, "R1", "T", None)
    assert p.runs[0].thresholds == {}
    ed.set_threshold(p, "R1", "T", None)  # nothing to remove is fine


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_set_threshold_refuses_non_positive(bad):
    p = make_project([("R1", "A1", "s", "T", "unknown", 20.0, None)])
    with pytest.raises(ValueError):
        ed.set_threshold(p, "R1", "T", bad)
    assert p.runs[0].thresholds == {}


def test_set_threshold_can_be_undone():
    p = make_project([("R1", "A1", "s", "T", "unknown", 20.0, None)])
    ed.set_threshold(p, "R1", "T", 0.2)
    history = ed.EditHistory()
    history.record(p)
    ed.set_threshold(p, "R1", "T", 0.5)
    assert history.undo(p).runs[0].thresholds == {"T": 0.2}

import json

import pytest

from qpcr_core.models import Curve
from qpcr_core.sessions import SessionError, load_project, project_from_dict, project_to_dict, save_project
from tests.factories import make_project


def _project():
    p = make_project(
        [
            ("R1", "A1", "s1", "GAPDH", "unknown", 20.0, None),
            ("R1", "A2", "s1", "GAPDH", "std", None, 100.0),
        ],
        groups={"s1": "Ctrl"},
        refs=("GAPDH",),
        control_group="Ctrl",
    )
    rxn = p.runs[0].wells["A2"].reactions[0]
    rxn.excluded = True
    rxn.exclude_reason = "bubble"
    p.runs[0].wells["A1"].reactions[0].amplification = Curve([1.0, 2.0], [0.1, 0.2])
    return p


def test_round_trip(tmp_path):
    p = _project()
    path = tmp_path / "x.qpcrkit.json"
    save_project(p, path)
    assert load_project(path) == p


def test_dict_round_trip():
    p = _project()
    assert project_from_dict(project_to_dict(p)) == p


def test_header(tmp_path):
    path = tmp_path / "x.qpcrkit.json"
    save_project(_project(), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["app"] == "qpcrkit"
    assert data["version"].count(".") == 2
    assert "project" in data


def test_second_save_makes_bak(tmp_path):
    path = tmp_path / "x.qpcrkit.json"
    p = _project()
    save_project(p, path)
    first = path.read_text(encoding="utf-8")
    p.settings.control_group = "Other"
    save_project(p, path)
    assert (tmp_path / "x.qpcrkit.json.bak").read_text(encoding="utf-8") == first


def test_broken_json_raises_with_path(tmp_path):
    path = tmp_path / "bad.qpcrkit.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SessionError, match="bad.qpcrkit.json"):
        load_project(path)


def test_foreign_app_rejected(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"app": "platekit", "version": "1.0.0", "project": {}}), encoding="utf-8")
    with pytest.raises(SessionError, match="plan.json"):
        load_project(path)


def test_unknown_keys_ignored():
    d = project_to_dict(_project())
    d["future_field"] = 1
    d["runs"][0]["future_field"] = 2
    d["runs"][0]["wells"]["A1"]["reactions"][0]["future_field"] = 3
    d["settings"]["future_field"] = 4
    assert project_from_dict(d) == _project()


def test_curves_lists_become_tuples_and_old_sessions_open():
    from qpcr_core.models import Curve

    assert Curve([1], [2]) == Curve((1,), (2,))
    p = _project()
    d = project_to_dict(p)
    rxn = d["runs"][0]["wells"]["A1"]["reactions"][0]
    rxn["amplification"] = {"x": [1.0, 2.0], "y": [0.1, 0.2]}
    rxn.pop("melt_derivative")
    rxn.pop("baseline_subtracted")
    assert project_from_dict(d) == p
    rxn["melt_derivative"] = {"x": [60.0], "y": [1.0]}
    assert project_from_dict(d).runs[0].wells["A1"].reactions[0].melt_derivative == Curve((60.0,), (1.0,))


# --- compact files ---


def _wendy():
    from pathlib import Path

    from qpcr_core.importers.detect import import_files
    from qpcr_core.models import Project

    real = Path(__file__).parent / "data" / "real"
    report = import_files(sorted(real.glob("2016-09-04*")), 1)[0]
    p = Project(runs=[report.run])
    p.ensure_targets_and_samples()
    return p


def test_curves_share_one_axis_in_the_file():
    d = project_to_dict(_wendy())["runs"][0]
    assert 1 <= len(d["curve_axes"]) <= 3
    first = next(iter(d["wells"].values()))["reactions"][0]["amplification"]
    assert "x" not in first and first["x_ref"] < len(d["curve_axes"])


def test_project_file_with_curves_is_small(tmp_path):
    path = tmp_path / "w.qpcrkit.json"
    save_project(_wendy(), path)
    assert path.stat().st_size < 350_000


def test_round_trip_keeps_the_analysis(tmp_path):
    from qpcr_core.pipeline import analyze

    p = _wendy()
    path = tmp_path / "w.qpcrkit.json"
    save_project(p, path)
    q = load_project(path)
    before, after = analyze(p).curves, analyze(q).curves
    assert before.keys() == after.keys()
    for key, r in before.items():
        assert after[key].cq_calc == pytest.approx(r.cq_calc, abs=1e-3)
    a, b = p.runs[0].wells["A1"].reactions[0].amplification, q.runs[0].wells["A1"].reactions[0].amplification
    assert b.x == a.x
    assert b.y == pytest.approx(a.y, rel=1e-6)


def test_loaded_curves_share_their_axis(tmp_path):
    path = tmp_path / "w.qpcrkit.json"
    save_project(_wendy(), path)
    wells = load_project(path).runs[0].wells
    assert wells["A1"].reactions[0].amplification.x is wells["A2"].reactions[0].amplification.x


def test_undo_redo_then_save_and_load(tmp_path):
    from qpcr_core.editing import EditHistory, set_excluded

    p = _wendy()
    curve = p.runs[0].wells["A1"].reactions[0].amplification
    history = EditHistory()
    history.record(p)
    set_excluded(p, p.runs[0].id, "A1", None, True, "test")
    undone = history.undo(p)
    assert not undone.runs[0].wells["A1"].reactions[0].excluded
    assert undone.runs[0].wells["A1"].reactions[0].amplification is curve  # snapshots share the curves
    redone = history.redo(undone)
    assert redone.runs[0].wells["A1"].reactions[0].amplification is curve
    path = tmp_path / "w.qpcrkit.json"
    save_project(redone, path)
    assert load_project(path).runs[0].wells["A1"].reactions[0].excluded


def test_old_file_with_curves_in_full_opens():
    p = _project()
    d = project_to_dict(p)
    run = d["runs"][0]
    axes = run.pop("curve_axes")
    rxn = run["wells"]["A1"]["reactions"][0]
    rxn["amplification"] = {"x": axes[rxn["amplification"]["x_ref"]], "y": rxn["amplification"]["y"]}
    assert project_from_dict(d).runs[0].wells["A1"].reactions[0].amplification == Curve([1.0, 2.0], [0.1, 0.2])


def test_file_of_1_0_without_curves_opens():
    d = {"runs": [{"id": "R", "name": "R", "wells": {"A1": {"coord": "A1", "reactions": [{"target": "T", "cq": 20.0}]}}}]}
    q = project_from_dict(d)
    assert q.runs[0].thresholds == {}
    assert q.settings.cq_source == "instrument"

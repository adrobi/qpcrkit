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

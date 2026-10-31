from pathlib import Path

from qpcr_core.editing import set_group
from tests.factories import make_project
from ui.editor import ProjectEditor


def _editor():
    return ProjectEditor(make_project([("R1", "A1", "s1", "IL6", "unknown", 20.0, None)]))


def test_apply_marks_dirty_and_emits(qapp):
    e = _editor()
    hits = []
    e.changed.connect(lambda: hits.append(1))
    e.apply(set_group, "s1", "LPS")
    assert e.project.samples["s1"].group == "LPS"
    assert e.dirty and hits == [1]


def test_undo_redo(qapp):
    e = _editor()
    e.apply(set_group, "s1", "LPS")
    assert e.undo() is True
    assert e.project.samples["s1"].group == ""
    assert e.undo() is False
    assert e.redo() is True
    assert e.project.samples["s1"].group == "LPS"


def test_mark_saved_and_set_project(qapp, tmp_path):
    e = _editor()
    e.apply(set_group, "s1", "LPS")
    e.mark_saved(tmp_path / "x.qpcrkit.json")
    assert not e.dirty and e.path == Path(tmp_path / "x.qpcrkit.json")
    e.set_project(make_project([]))
    assert e.undo() is False and e.path is None and not e.dirty

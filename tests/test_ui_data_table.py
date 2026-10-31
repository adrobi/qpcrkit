from PySide6.QtCore import Qt

from tests.factories import make_project
from ui.data_table import COLUMNS, DataTable, ReactionModel
from ui.editor import ProjectEditor


def _editor():
    return ProjectEditor(make_project([
        ("R1", "A1", "s1", "GAPDH", "unknown", 20.0, None),
        ("R1", "A1", "s1", "IL6", "unknown", 25.0, None),
        ("R1", "A2", "s2", "IL6", "std", 22.0, 100.0),
    ]))


def test_columns():
    assert COLUMNS == ("run", "well", "sample", "group", "target", "role", "cq", "quantity", "excluded")


def test_row_count(qapp):
    assert ReactionModel(_editor()).rowCount() == 3


def test_edit_group(qapp):
    e = _editor()
    m = ReactionModel(e)
    assert m.setData(m.index(0, COLUMNS.index("group")), "LPS", Qt.ItemDataRole.EditRole)
    assert e.project.samples["s1"].group == "LPS" and e.dirty


def test_edit_quantity_and_role(qapp):
    e = _editor()
    m = ReactionModel(e)
    m.setData(m.index(2, COLUMNS.index("quantity")), "1e3", Qt.ItemDataRole.EditRole)
    assert e.project.run("R1").wells["A2"].reactions[0].quantity == 1000.0
    m.setData(m.index(1, COLUMNS.index("role")), "ntc", Qt.ItemDataRole.EditRole)
    gapdh, il6 = e.project.run("R1").wells["A1"].reactions
    assert (gapdh.role, il6.role) == ("unknown", "ntc")


def test_exclude_checkbox(qapp):
    e = _editor()
    m = ReactionModel(e)
    idx = m.index(1, COLUMNS.index("excluded"))
    assert m.flags(idx) & Qt.ItemFlag.ItemIsUserCheckable
    m.setData(idx, Qt.CheckState.Checked.value, Qt.ItemDataRole.CheckStateRole)
    assert e.project.run("R1").wells["A1"].reactions[1].excluded
    assert not e.project.run("R1").wells["A1"].reactions[0].excluded


def test_cq_not_editable(qapp):
    m = ReactionModel(_editor())
    assert not m.flags(m.index(0, COLUMNS.index("cq"))) & Qt.ItemFlag.ItemIsEditable


def test_model_follows_undo(qapp):
    e = _editor()
    m = ReactionModel(e)
    m.setData(m.index(0, COLUMNS.index("group")), "LPS", Qt.ItemDataRole.EditRole)
    e.undo()
    assert m.data(m.index(0, COLUMNS.index("group"))) == ""


def test_paste_and_filter(qapp):
    e = _editor()
    t = DataTable(e)
    assert t.paste_sample_table("s1\tLPS\ns2\tCtrl\n") == 2
    assert e.project.samples["s2"].group == "Ctrl"
    t.set_filter("il6")
    assert t.visible_row_count() == 2
    t.set_filter("")
    assert t.visible_row_count() == 3


def test_cq_sorts_numerically(qapp):
    e = ProjectEditor(make_project([
        ("R1", "A1", "s1", "IL6", "unknown", 20.0, None),
        ("R1", "A2", "s1", "IL6", "unknown", 9.5, None),
        ("R1", "A3", "s1", "IL6", "unknown", None, None),
    ]))
    t = DataTable(e)
    t.table.sortByColumn(COLUMNS.index("cq"), Qt.SortOrder.AscendingOrder)
    col = COLUMNS.index("cq")
    assert [t.proxy.index(r, col).data() for r in range(3)] == ["9.50", "20.00", "—"]

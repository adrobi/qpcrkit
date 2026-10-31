from qpcr_core.importers.generic_csv import ColumnMapping
from ui.csv_wizard import CsvWizard

ROWS = [["Pos", "Gene", "Ct", "Name"], ["A1", "IL6", "20", "s1"]]


def test_mapping_from_combos(qapp):
    w = CsvWizard(ROWS, {})
    for field, col in (("well", "Pos"), ("target", "Gene"), ("cq", "Ct")):
        w.combos[field].setCurrentIndex(w.combos[field].findData(col))
    w.accept()
    assert w.mapping() == ColumnMapping(well="Pos", target="Gene", cq="Ct")


def test_guess_by_names(qapp):
    w = CsvWizard([["Well", "Target", "Cq", "Sample"], ["A1", "IL6", "20", "s1"]], {})
    w.accept()
    assert w.mapping() == ColumnMapping(well="Well", target="Target", cq="Cq", sample="Sample")


def test_reject_gives_none(qapp):
    w = CsvWizard(ROWS, {})
    w.reject()
    assert w.mapping() is None


def test_missing_required_gives_none(qapp):
    w = CsvWizard([["Pos", "Gene", "Value"], ["A1", "IL6", "20"]], {})
    w.accept()
    assert w.mapping() is None


def test_preset_applied_and_saved(qapp):
    preset = ColumnMapping(well="Pos", target="Gene", cq="Ct", sample="Name").to_dict()
    w = CsvWizard(ROWS, {"lab": preset})
    w.preset_combo.setCurrentIndex(w.preset_combo.findData("lab"))
    w.preset_name.setText("lab2")
    w.accept()
    assert w.mapping() == ColumnMapping.from_dict(preset)
    assert w.preset_to_save() == ("lab2", preset)


def test_invalid_accept_keeps_dialog_open(qapp):
    from PySide6.QtWidgets import QDialog

    w = CsvWizard([["Pos", "Gene", "Value"], ["A1", "IL6", "20"]], {})
    w.show()
    w.accept()
    assert w.isVisible() and w.result() != QDialog.DialogCode.Accepted


def test_ct_header_guessed(qapp):
    w = CsvWizard([["Well", "Target", "Ct"], ["A1", "IL6", "20"]], {})
    w.accept()
    assert w.mapping() == ColumnMapping(well="Well", target="Target", cq="Ct")

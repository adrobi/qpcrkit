"""Dialog mapping arbitrary table columns to a generic CSV import mapping."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qpcr_core.importers.generic_csv import ColumnMapping

from i18n import tr

FIELDS = ("well", "target", "cq", "sample", "role", "quantity", "group")
REQUIRED = ("well", "target", "cq")

ALIASES: dict[str, set[str]] = {
    "well": {"well", "well position", "position", "лунка"},
    "target": {"target", "target name", "assay", "мишень"},
    "cq": {"cq", "ct", "cт", "c(t)"},
    "sample": {"sample", "sample name", "образец"},
    "role": {"role", "content", "task", "type", "роль"},
    "quantity": {
        "quantity",
        "sq",
        "starting quantity",
        "starting quantity (sq)",
        "given conc",
        "количество",
    },
    "group": {"group", "biological set name", "biogroup name", "группа"},
}


class CsvWizard(QDialog):
    """Map table columns to an import mapping, with optional presets."""

    combos: dict[str, QComboBox]
    header_spin: QSpinBox
    preset_combo: QComboBox
    preset_name: QLineEdit

    def __init__(
        self,
        rows: list[list[str]],
        presets: dict[str, dict],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._rows = rows
        self._presets = presets
        self._result: ColumnMapping | None = None
        self._accepted = False

        self.setWindowTitle(tr("ui.wizard.title"))

        self.header_spin = QSpinBox(self)
        last = max(0, min(len(rows) - 1, 50)) if rows else 0
        self.header_spin.setRange(0, last)

        self.preset_combo = QComboBox(self)
        self.preset_combo.addItem(tr("ui.none"), None)
        for name in presets:
            self.preset_combo.addItem(name, name)

        self.preset_name = QLineEdit(self)
        self.error_label = QLabel(tr("ui.wizard.required"), self)
        self.error_label.hide()

        self.preview = QTableWidget(self)
        self.preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview.setSelectionMode(QAbstractItemView.NoSelection)

        top = QFormLayout()
        top.addRow(tr("ui.wizard.header_row"), self.header_spin)
        top.addRow(tr("ui.wizard.preset"), self.preset_combo)

        fields = QFormLayout()
        self.combos = {}
        for field in FIELDS:
            combo = QComboBox(self)
            label = QLabel(tr(f"ui.field.{field}"), self)
            if field in REQUIRED:
                label.setStyleSheet("font-weight: bold")
            fields.addRow(label, combo)
            self.combos[field] = combo

        save = QFormLayout()
        save.addRow(tr("ui.wizard.save_preset"), self.preset_name)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(fields)
        layout.addWidget(self.preview)
        layout.addLayout(save)
        layout.addWidget(self.error_label)
        layout.addWidget(buttons)

        self.header_spin.valueChanged.connect(self._on_header_changed)
        self.preset_combo.currentIndexChanged.connect(self._apply_preset)
        self._on_header_changed(self.header_spin.value())

    def mapping(self) -> ColumnMapping | None:
        """Return the accepted mapping, or None."""
        return self._result

    def preset_to_save(self) -> tuple[str, dict] | None:
        """Return a preset name and mapping when accepted and valid."""
        if not self._accepted or self._result is None:
            return None
        name = self.preset_name.text().strip()
        if not name:
            return None
        return name, self._result.to_dict()

    def accept(self) -> None:
        """Build a mapping; stay open with an error while required fields are missing."""
        self._result = self._build_mapping()
        self._accepted = self._result is not None
        self.error_label.setVisible(self._result is None)
        if self._result is not None:
            super().accept()

    def reject(self) -> None:
        """Close without a mapping."""
        self._result = None
        self._accepted = False
        super().reject()

    def _header(self, row: int) -> list[str]:
        if 0 <= row < len(self._rows):
            return [str(cell) for cell in self._rows[row]]
        return []

    def _on_header_changed(self, row: int) -> None:
        header = self._header(row)
        for field, combo in self.combos.items():
            combo.clear()
            combo.addItem(tr("ui.none"), None)
            for cell in header:
                combo.addItem(cell, cell)
        self._guess(header)
        self._update_preview(header)

    def _guess(self, header: list[str]) -> None:
        normalized = [(cell.strip().lower(), cell) for cell in header]
        for field in FIELDS:
            combo = self.combos[field]
            match = next(
                (original for text, original in normalized if text in ALIASES[field]),
                None,
            )
            index = combo.findData(match) if match is not None else -1
            combo.setCurrentIndex(index if index >= 0 else 0)

    def _update_preview(self, header: list[str]) -> None:
        self.preview.clear()
        self.preview.setColumnCount(len(header))
        self.preview.setHorizontalHeaderLabels(header)

        header_row = self.header_spin.value()
        data_rows = (
            self._rows[header_row + 1 : header_row + 11]
            if 0 <= header_row < len(self._rows)
            else []
        )
        self.preview.setRowCount(len(data_rows))
        for r, row in enumerate(data_rows):
            for c in range(len(header)):
                value = row[c] if c < len(row) else ""
                self.preview.setItem(r, c, QTableWidgetItem(str(value)))

    def _apply_preset(self, index: int) -> None:
        name = self.preset_combo.itemData(index)
        if not isinstance(name, str):
            return
        preset = self._presets.get(name)
        if preset is None:
            return

        try:
            header_row = int(preset.get("header_row", 0))
        except (TypeError, ValueError):
            header_row = 0
        self.header_spin.setValue(header_row)

        for field in FIELDS:
            combo = self.combos[field]
            value = preset.get(field)
            if value is None:
                combo.setCurrentIndex(0)
            else:
                found = combo.findData(value)
                combo.setCurrentIndex(found if found >= 0 else 0)

    def _build_mapping(self) -> ColumnMapping | None:
        values = {
            field: self.combos[field].currentData()
            for field in FIELDS
        }
        if any(values[field] is None for field in REQUIRED):
            return None
        return ColumnMapping(
            well=values["well"],
            target=values["target"],
            cq=values["cq"],
            sample=values["sample"],
            role=values["role"],
            quantity=values["quantity"],
            group=values["group"],
            header_row=self.header_spin.value(),
        )

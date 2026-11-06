"""The panel under the plate: what the selected wells hold, and the fields to change it."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QGridLayout, QLabel, QLineEdit, QPushButton, QWidget

from i18n import tr
from qpcr_core.models import ROLES, Project, Run


class SelectionPanel(QWidget):
    apply_requested = Signal()
    series_requested = Signal()
    exclude_requested = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = QLabel()
        self.label.setObjectName("dim")
        self.target_edit = QLineEdit()
        self.sample_edit = QLineEdit()
        self.group_edit = QLineEdit()
        self.quantity_edit = QLineEdit()
        self.role_combo = QComboBox()
        self.role_combo.addItem(tr("ui.none"), None)  # leave roles unchanged
        for role in ROLES:
            self.role_combo.addItem(tr(f"ui.role.{role}"), role)
        self.apply_button = QPushButton(tr("ui.apply"))
        self.apply_button.setObjectName("primaryBtn")
        self.series_button = QPushButton(tr("ui.series"))
        self.exclude_button = QPushButton(tr("ui.exclude"))
        self.include_button = QPushButton(tr("ui.include"))

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 6, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        grid.addWidget(self.label, 0, 0, 1, 4)
        for column, widget in enumerate((self.target_edit, self.sample_edit, self.group_edit, self.quantity_edit)):
            grid.addWidget(widget, 1, column)
        grid.addWidget(self.role_combo, 2, 0)
        grid.addWidget(self.apply_button, 2, 1)
        grid.addWidget(self.series_button, 2, 2)
        exclude_box = QWidget()
        exclude_row = QGridLayout(exclude_box)
        exclude_row.setContentsMargins(0, 0, 0, 0)
        exclude_row.setHorizontalSpacing(6)
        exclude_row.addWidget(self.exclude_button, 0, 0)
        exclude_row.addWidget(self.include_button, 0, 1)
        grid.addWidget(exclude_box, 2, 3)

        self.apply_button.clicked.connect(lambda: self.apply_requested.emit())
        self.series_button.clicked.connect(lambda: self.series_requested.emit())
        self.exclude_button.clicked.connect(lambda: self.exclude_requested.emit(True))
        self.include_button.clicked.connect(lambda: self.exclude_requested.emit(False))
        for edit in (self.target_edit, self.sample_edit, self.group_edit, self.quantity_edit):
            edit.returnPressed.connect(lambda: self.apply_requested.emit())
        self.set_selection(None, None, [])

    def _fields(self) -> tuple[QWidget, ...]:
        return (
            self.target_edit, self.sample_edit, self.group_edit, self.quantity_edit, self.role_combo,
            self.apply_button, self.series_button, self.exclude_button, self.include_button,
        )

    def set_selection(self, project: Project | None, run: Run | None, coords: list[str]) -> None:
        """Show what the wells hold as placeholders. Typed text stays: it may be meant for the next selection."""
        active = bool(project and run and coords)
        for widget in self._fields():
            widget.setEnabled(active)
        self.label.setText(tr("ui.selection", n=len(coords)) if active else tr("ui.select_wells"))
        wells = [run.wells[c] for c in coords if c in run.wells] if active else []
        rxns = [r for w in wells for r in w.reactions]
        samples = [w.sample or "" for w in wells]
        groups = [
            (project.samples[w.sample].group or "") if w.sample and w.sample in project.samples else ""
            for w in wells
        ]
        quantities = [f"{r.quantity:g}" if r.quantity is not None else "" for r in rxns]
        for edit, values, name in (
            (self.target_edit, [r.target for r in rxns], "ui.target"),
            (self.sample_edit, samples, "ui.col.sample"),
            (self.group_edit, groups, "ui.col.group"),
            (self.quantity_edit, quantities, "ui.col.quantity"),
        ):
            edit.setPlaceholderText(self._summary(values, tr(name)))

    @staticmethod
    def _summary(values: list[str], empty: str) -> str:
        distinct = set(values)
        if len(distinct) > 1:
            return tr("ui.mixed")
        return next(iter(distinct)) if distinct and next(iter(distinct)) else empty

    def clear_fields(self) -> None:
        for edit in (self.target_edit, self.sample_edit, self.group_edit, self.quantity_edit):
            edit.clear()
        self.role_combo.setCurrentIndex(0)

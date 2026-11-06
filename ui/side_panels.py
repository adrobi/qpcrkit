"""The list of runs in the navigation, and the settings form of the analysis dialog."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from i18n import tr
from qpcr_core.editing import update_settings
from qpcr_core.models import Project
from qpcr_core.pipeline import Results
from ui.editor import ProjectEditor
from ui.theme import DARK, LIGHT, icon


def _set_efficiency(project: Project, target: str, mode: str, manual: float | None) -> None:
    """Set a target's efficiency mode and optional manual fraction."""
    t = project.targets[target]
    t.efficiency_mode = mode
    t.efficiency_manual = manual


class ProjectTree(QWidget):
    """The runs of the project, with a button to add one."""

    run_selected = Signal(str)
    add_run_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._run_items: dict[str, QTreeWidgetItem] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel(tr("ui.runs"))
        title.setObjectName("dim")
        layout.addWidget(title)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.setRootIsDecorated(False)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        layout.addWidget(self.tree, 1)

        self.add_run_button = QPushButton(tr("ui.add_run"), self)
        layout.addWidget(self.add_run_button)

        self.tree.itemClicked.connect(self._on_item_clicked)
        self.add_run_button.clicked.connect(lambda: self.add_run_requested.emit())

    def refresh(self, project: Project) -> None:
        """Rebuild the list from *project*."""
        self.tree.clear()
        self._run_items.clear()
        for run in project.runs:
            item = QTreeWidgetItem([run.name or run.id])
            item.setToolTip(0, f"{run.id} · {run.name} ({run.instrument}, {tr('ui.wells_n', n=len(run.wells))})")
            item.setData(0, Qt.ItemDataRole.UserRole, run.id)
            self.tree.addTopLevelItem(item)
            self._run_items[run.id] = item

    def set_current_run(self, run_id: str | None) -> None:
        item = self._run_items.get(run_id) if run_id else None
        if item is not None:
            self.tree.setCurrentItem(item)

    def set_theme(self, dark: bool) -> None:
        self.add_run_button.setIcon(icon("plus", (DARK if dark else LIGHT)["dim"]))

    def run_item(self, run_id: str) -> QTreeWidgetItem | None:
        """Return the list item for *run_id*, if present."""
        return self._run_items.get(run_id)

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        run_id = item.data(0, Qt.ItemDataRole.UserRole)
        if run_id is not None:
            self.run_selected.emit(str(run_id))


class SettingsPanel(QWidget):
    """Scrollable form: efficiency per target, test, QC thresholds. Lives in the analysis dialog."""

    def __init__(self, editor: ProjectEditor) -> None:
        super().__init__()
        self.editor = editor
        self._target_names: tuple[str, ...] | None = None
        self.eff_mode: dict[str, QComboBox] = {}
        self.eff_value: dict[str, QDoubleSpinBox] = {}
        self.curve_eff_label: dict[str, QLabel] = {}
        self._results: Results | None = None
        self.spins: dict[str, QDoubleSpinBox] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        content = QWidget()
        self._form = QFormLayout(content)
        self._form.setContentsMargins(8, 8, 8, 8)
        scroll.setWidget(content)

        self._add_title(tr("ui.cq_source"))
        self.cq_source_combo = QComboBox()
        self.cq_source_combo.addItem(tr("ui.cq_source.instrument"), "instrument")
        self.cq_source_combo.addItem(tr("ui.cq_source.calculated"), "calculated")
        self._form.addRow(self.cq_source_combo)

        self._add_title(tr("ui.efficiency"))
        self._eff_box = QWidget()
        self._eff_layout = QVBoxLayout(self._eff_box)
        self._eff_layout.setContentsMargins(0, 0, 0, 0)
        self._form.addRow(self._eff_box)

        self._add_title(tr("ui.test"))
        self.test_combo = QComboBox()
        self.test_combo.addItem(tr("ui.test.dunnett"), "dunnett")
        self.test_combo.addItem(tr("ui.test.tukey"), "tukey")
        self._form.addRow(self.test_combo)

        self._add_title(tr("ui.thresholds"))
        specs = (
            ("rep_sd_max", 0.0, 5.0, 0.05, 2),
            ("ntc_cq_min", 0.0, 60.0, 0.5, 1),
            ("late_cq", 0.0, 60.0, 0.5, 1),
            ("eff_min", 0.0, 2.0, 0.01, 2),
            ("eff_max", 0.0, 2.0, 0.01, 2),
            ("r2_min", 0.0, 1.0, 0.005, 3),
            ("nrt_min_delta", 0.0, 30.0, 0.5, 1),
            ("tm_shift_max", 0.0, 10.0, 0.1, 1),
            ("early_cq", 0.0, 30.0, 0.5, 1),
            ("cq_disagree_max", 0.0, 10.0, 0.1, 1),
        )
        for name, minimum, maximum, step, decimals in specs:
            spin = QDoubleSpinBox()
            spin.setRange(minimum, maximum)
            spin.setSingleStep(step)
            spin.setDecimals(decimals)
            self.spins[name] = spin
            self._form.addRow(QLabel(tr(f"ui.set.{name}")), spin)

        self.pool_check = QCheckBox(tr("ui.pool_std_runs"))
        self._form.addRow(self.pool_check)

        self.test_combo.currentIndexChanged.connect(self._test_changed)
        self.cq_source_combo.currentIndexChanged.connect(self._cq_source_changed)
        for name, spin in self.spins.items():
            spin.valueChanged.connect(lambda value, n=name: self._spin_changed(n, value))
        self.pool_check.toggled.connect(self._pool_toggled)

        editor.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        """Sync widgets with ``editor.project`` without recording edits."""
        project = self.editor.project
        names = tuple(sorted(project.targets))
        if names != self._target_names:
            self._rebuild_target_widgets(names)
            self._target_names = names

        with QSignalBlocker(self.test_combo):
            index = self.test_combo.findData(project.settings.test)
            self.test_combo.setCurrentIndex(index if index >= 0 else 0)

        with QSignalBlocker(self.cq_source_combo):
            index = self.cq_source_combo.findData(project.settings.cq_source)
            self.cq_source_combo.setCurrentIndex(index if index >= 0 else 0)

        for name, spin in self.spins.items():
            with QSignalBlocker(spin):
                spin.setValue(getattr(project.settings, name))

        with QSignalBlocker(self.pool_check):
            self.pool_check.setChecked(bool(project.settings.pool_std_runs))

        for name, combo in self.eff_mode.items():
            target = project.targets.get(name)
            mode = target.efficiency_mode if target else "stdcurve"
            with QSignalBlocker(combo):
                index = combo.findData(mode)
                combo.setCurrentIndex(index if index >= 0 else 0)
            spin = self.eff_value[name]
            with QSignalBlocker(spin):
                value = target.efficiency_manual if target and target.efficiency_manual is not None else 1.0
                spin.setValue(value)
                spin.setEnabled(mode == "manual")
        self._apply_results()

    def set_results(self, results: Results | None) -> None:
        """Kept, because a refresh may rebuild the rows of the targets."""
        self._results = results
        self._apply_results()

    def _apply_results(self) -> None:
        """What the curves say about each target; their mode needs an estimate, unless already chosen."""
        known = self._results.curve_efficiency if self._results else {}
        for name, combo in self.eff_mode.items():
            value = known.get(name)
            self.curve_eff_label[name].setText(tr("ui.eff.from_curves", eff=value) if value is not None else "")
            item = combo.model().item(combo.findData("curves"))
            item.setEnabled(value is not None or combo.currentData() == "curves")

    def _add_title(self, text: str) -> None:
        label = QLabel(text)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        self._form.addRow(label)

    def _rebuild_target_widgets(self, names: tuple[str, ...]) -> None:
        _clear_layout(self._eff_layout)
        self.eff_mode = {}
        self.eff_value = {}
        self.curve_eff_label = {}
        for name in names:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(QLabel(name), 1)

            mode = QComboBox()
            mode.addItem(tr("ui.eff.stdcurve"), "stdcurve")
            mode.addItem(tr("ui.eff.curves"), "curves")
            mode.addItem(tr("ui.eff.manual"), "manual")
            mode.addItem(tr("ui.eff.ideal"), "ideal")
            mode.currentIndexChanged.connect(lambda _index, n=name: self._eff_mode_changed(n))
            row_layout.addWidget(mode)

            value = QDoubleSpinBox()
            value.setRange(0.5, 1.5)
            value.setSingleStep(0.01)
            value.setDecimals(3)
            value.setEnabled(False)
            value.valueChanged.connect(lambda v, n=name: self._eff_value_changed(n, v))
            row_layout.addWidget(value)

            estimate = QLabel()
            estimate.setObjectName("dim")
            row_layout.addWidget(estimate)

            self._eff_layout.addWidget(row)
            self.eff_mode[name] = mode
            self.eff_value[name] = value
            self.curve_eff_label[name] = estimate

    def _cq_source_changed(self, _index: int) -> None:
        value = self.cq_source_combo.currentData() or "instrument"
        if value != self.editor.project.settings.cq_source:
            self.editor.apply(update_settings, cq_source=value)

    def _test_changed(self, _index: int) -> None:
        value = self.test_combo.currentData() or "dunnett"
        if value != self.editor.project.settings.test:
            self.editor.apply(update_settings, test=value)

    def _spin_changed(self, name: str, value: float) -> None:
        if getattr(self.editor.project.settings, name) != value:
            self.editor.apply(update_settings, **{name: value})

    def _pool_toggled(self, checked: bool) -> None:
        if self.editor.project.settings.pool_std_runs != checked:
            self.editor.apply(update_settings, pool_std_runs=checked)

    def _eff_mode_changed(self, name: str) -> None:
        target = self.editor.project.targets.get(name)
        if target is None:
            return
        mode = self.eff_mode[name].currentData() or "stdcurve"
        spin = self.eff_value[name]
        manual = spin.value() if mode == "manual" else None
        if target.efficiency_mode != mode or (
            mode == "manual" and target.efficiency_manual != manual
        ):
            self.editor.apply(_set_efficiency, name, mode, manual)

    def _eff_value_changed(self, name: str, value: float) -> None:
        target = self.editor.project.targets.get(name)
        if target is None:
            return
        if target.efficiency_mode != "manual" or target.efficiency_manual != value:
            self.editor.apply(_set_efficiency, name, "manual", value)


def _clear_layout(layout: QLayout) -> None:
    """Delete all widgets from a layout."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        else:
            child = item.layout()
            if child is not None:
                _clear_layout(child)

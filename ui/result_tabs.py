"""Result views: standard curves, relative expression, QC flags."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from i18n import tr
from qpcr_core.editing import update_settings
from qpcr_core.figures import expression_figure, std_curve_figure
from qpcr_core.flags import Flag, flag_text
from qpcr_core.models import Project
from qpcr_core.pipeline import Results
from ui.canvas import FigureCanvas
from ui.editor import ProjectEditor
from ui.theme import mpl_style, theme

_ERROR_KINDS = ("sd", "sem", "ci95")


def failure_label(layout) -> QLabel:
    """The line that says the analysis failed; hidden until it does."""
    label = QLabel()
    label.setObjectName("dim")
    label.setWordWrap(True)
    label.hide()
    layout.insertWidget(0, label)
    return label


def _table(widget: QTableWidget, headers: list[str], rows: list[list[object]]) -> None:
    """Fill a compact read-only table."""
    widget.setColumnCount(len(headers))
    widget.setRowCount(len(rows))
    widget.setHorizontalHeaderLabels(headers)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            if value is None:
                text = ""
            elif isinstance(value, float):
                text = f"{value:.4g}"
            else:
                text = str(value)
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            widget.setItem(row_index, column_index, item)
    widget.verticalHeader().setVisible(False)
    widget.horizontalHeader().setStretchLastSection(True)
    widget.resizeColumnsToContents()


class StdCurveTab(QWidget):
    """Standard-curve figure and table."""

    point_clicked = Signal(str, str, str)  # run, well, target

    def __init__(self) -> None:
        super().__init__()
        self._project: Project | None = None
        self._results: Results | None = None
        self._dark = False
        self._curves: list[tuple[tuple[str | None, str], object]] = []
        self._headers = [
            tr("ui.target"),
            tr("ui.col.run"),
            tr("ui.col.slope"),
            tr("ui.col.intercept"),
            tr("ui.col.r2"),
            tr("ui.col.efficiency"),
            tr("ui.col.lowest"),
        ]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._combo = QComboBox()
        self._combo.currentIndexChanged.connect(self._on_curve_changed)
        layout.addWidget(self._combo)
        self.failure = failure_label(layout)

        self._canvas = FigureCanvas(tr("ui.no_curves"))
        self._table_widget = QTableWidget()
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(self._canvas)
        self.splitter.addWidget(self._table_widget)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([3000, 800])
        layout.addWidget(self.splitter, 1)

        _table(self._table_widget, self._headers, [])

    def set_results(self, project: Project, results: Results, dark: bool) -> None:
        """Show the standard curves for the current results."""
        self.failure.hide()
        self._project = project
        self._results = results
        self._dark = dark

        items = sorted(results.std_curves.items(), key=lambda kv: (kv[0][1], kv[0][0] or ""))
        self._curves = list(items)

        rows: list[list[object]] = []
        for (run_id, target), curve in items:
            rows.append(
                [
                    target,
                    run_id or tr("ui.pooled"),
                    curve.slope,
                    curve.intercept,
                    curve.r2,
                    f"{curve.efficiency:.1%}",
                    curve.lowest_detected,
                ]
            )

        previous = self._combo.currentText()
        blocker = QSignalBlocker(self._combo)
        self._combo.clear()
        for index, ((run_id, target), _curve) in enumerate(items):
            run_label = run_id or tr("ui.pooled")
            self._combo.addItem(f"{target} — {run_label}", index)
        if items:
            self._combo.setCurrentIndex(max(self._combo.findText(previous), 0))
        else:
            self._combo.setCurrentIndex(-1)
        blocker.unblock()

        _table(self._table_widget, self._headers, rows)
        self._draw_current()

    def show_failure(self, text: str) -> None:
        self._curves = []
        with QSignalBlocker(self._combo):
            self._combo.clear()
        _table(self._table_widget, self._headers, [])
        self._canvas.set_figure(None)
        self.failure.setText(text)
        self.failure.show()

    def curve_count(self) -> int:
        """Return the number of available standard curves."""
        return len(self._curves)

    def _on_curve_changed(self, _index: int) -> None:
        self._draw_current()

    def _draw_current(self) -> None:
        index = self._combo.currentIndex()
        if index < 0 or index >= len(self._curves):
            self._canvas.set_figure(None)
            return
        curve = self._curves[index][1]
        self._canvas.set_figure(std_curve_figure(curve, style=mpl_style(self._dark)))  # type: ignore[arg-type]
        self._canvas.mpl_canvas.mpl_connect("pick_event", self._on_pick)

    def _on_pick(self, event) -> None:
        index = self._combo.currentIndex()
        if event.mouseevent.button != 1 or not 0 <= index < len(self._curves) or not len(event.ind):
            return
        curve = self._curves[index][1]
        point = curve.points[int(event.ind[0])]
        self.point_clicked.emit(point.run_id, point.coord, curve.target)


class ExpressionTab(QWidget):
    """Relative-expression figure and tables."""

    save_requested = Signal(str)  # target

    def __init__(self, editor: ProjectEditor) -> None:
        super().__init__()
        self._editor = editor
        self._project: Project | None = None
        self._results: Results | None = None
        self._dark = False
        self._target = ""
        self._log2 = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        controls = QHBoxLayout()
        self._target_combo = QComboBox()
        self._target_combo.currentIndexChanged.connect(self._on_target_changed)
        controls.addWidget(self._target_combo)

        self._error_combo = QComboBox()
        self._error_combo.addItem(tr("ui.error.sd"), "sd")
        self._error_combo.addItem(tr("ui.error.sem"), "sem")
        self._error_combo.addItem(tr("ui.error.ci95"), "ci95")
        self._set_error_combo(self._project_error_bar(editor.project))
        self._error_combo.currentIndexChanged.connect(self._on_error_changed)
        controls.addWidget(self._error_combo)

        self._log2_check = QCheckBox(tr("ui.log2"))
        self._log2_check.toggled.connect(self.set_log2)
        controls.addWidget(self._log2_check)
        controls.addStretch(1)
        self.save_button = QPushButton(tr("ui.save_figure"))
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(lambda: self.save_requested.emit(self._target))
        controls.addWidget(self.save_button)
        self.failure = failure_label(layout)
        layout.addLayout(controls)

        self._canvas = FigureCanvas(tr("ui.no_groups"))
        layout.addWidget(self._canvas, 3)

        self._groups_table = QTableWidget()
        self._comparisons_table = QTableWidget()
        layout.addWidget(self._groups_table, 1)
        layout.addWidget(self._comparisons_table, 1)

        self._redraw()

    def set_results(self, project: Project, results: Results, dark: bool) -> None:
        """Show relative-expression results."""
        self.failure.hide()
        self._project = project
        self._results = results
        self._dark = dark

        targets = sorted({group.target for group in results.groups})
        previous = self._target
        blocker = QSignalBlocker(self._target_combo)
        self._target_combo.clear()
        for target in targets:
            self._target_combo.addItem(target, target)
        if targets:
            index = self._target_combo.findData(previous)
            self._target_combo.setCurrentIndex(index if index >= 0 else 0)
            data = self._target_combo.currentData()
            self._target = "" if data is None else str(data)
        else:
            self._target_combo.setCurrentIndex(-1)
            self._target = ""
        blocker.unblock()

        self._set_error_combo(self._project_error_bar(project))
        self.save_button.setEnabled(bool(self._target))
        self._redraw()

    def show_failure(self, text: str) -> None:
        self._results = None
        self._target = ""
        with QSignalBlocker(self._target_combo):
            self._target_combo.clear()
        self._canvas.set_figure(None)
        _table(self._groups_table, [], [])
        _table(self._comparisons_table, [], [])
        self.save_button.setEnabled(False)
        self.failure.setText(text)
        self.failure.show()

    @property
    def log2(self) -> bool:
        return self._log2

    def set_error_bar(self, kind: str) -> None:
        """Select the error-bar kind and persist the setting when needed."""
        if kind not in _ERROR_KINDS:
            return
        combo_changed = self._error_combo.currentData() != kind
        if combo_changed:
            self._set_error_combo(kind)
        current = self._project_error_bar(self._editor.project)
        if kind != current:
            self._editor.apply(update_settings, error_bar=kind)
        elif combo_changed:
            self._redraw()

    def set_log2(self, on: bool) -> None:
        """Toggle log2 display and redraw when the value changes."""
        on = bool(on)
        changed = self._log2 != on
        self._log2 = on
        if self._log2_check.isChecked() != on:
            blocker = QSignalBlocker(self._log2_check)
            self._log2_check.setChecked(on)
            blocker.unblock()
        if changed:
            self._redraw()

    @staticmethod
    def _project_error_bar(project: Project) -> str:
        kind = getattr(project.settings, "error_bar", "sd")
        return kind if kind in _ERROR_KINDS else "sd"

    def _current_error_bar(self) -> str:
        kind = self._error_combo.currentData()
        return kind if kind in _ERROR_KINDS else "sd"

    def _set_error_combo(self, kind: str) -> None:
        index = self._error_combo.findData(kind)
        if index < 0:
            index = 0
        blocker = QSignalBlocker(self._error_combo)
        self._error_combo.setCurrentIndex(index)
        blocker.unblock()

    @staticmethod
    def _group_headers(kind: str) -> list[str]:
        return [
            tr("ui.col.group"),
            tr("ui.col.n"),
            tr("ui.col.fold"),
            f"{tr(f'ui.error.{kind}')} (log2)",
        ]

    @staticmethod
    def _comparison_headers() -> list[str]:
        return [
            tr("ui.col.group"),
            tr("ui.col.group_b"),
            tr("ui.col.test"),
            "t / F / q",
            tr("ui.col.p"),
            tr("ui.col.p_adj"),
        ]

    def _redraw(self) -> None:
        kind = self._current_error_bar()
        group_headers = self._group_headers(kind)
        comparison_headers = self._comparison_headers()

        if self._results is None or not self._target:
            self._canvas.set_figure(None)
            _table(self._groups_table, group_headers, [])
            _table(self._comparisons_table, comparison_headers, [])
            return

        groups = [group for group in self._results.groups if group.target == self._target]
        comparisons = [comparison for comparison in self._results.comparisons if comparison.target == self._target]

        group_rows = [
            [group.group, group.n, group.fold, getattr(group, f"{kind}_log2", None)]
            for group in groups
        ]
        comparison_rows = [
            [
                comparison.group_a,
                comparison.group_b,
                comparison.test,
                comparison.statistic,
                comparison.p,
                comparison.p_adj,
            ]
            for comparison in comparisons
        ]

        _table(self._groups_table, group_headers, group_rows)
        _table(self._comparisons_table, comparison_headers, comparison_rows)

        if groups:
            self._canvas.set_figure(
                expression_figure(
                    self._results,
                    self._target,
                    error=kind,
                    log2=self._log2,
                    style=mpl_style(self._dark),
                )
            )
        else:
            self._canvas.set_figure(None)

    def _on_target_changed(self, index: int) -> None:
        if index < 0:
            self._target = ""
        else:
            data = self._target_combo.itemData(index)
            self._target = "" if data is None else str(data)
        self._redraw()

    def _on_error_changed(self, index: int) -> None:
        kind = self._error_combo.itemData(index)
        if kind in _ERROR_KINDS:
            self.set_error_bar(str(kind))


class QcTab(QWidget):
    """QC flag tree with navigation to the affected well."""

    locate = Signal(str, str)
    _SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

    def __init__(self) -> None:
        super().__init__()
        self._flags: list[Flag] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._empty_label = QLabel(tr("ui.no_flags"))
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setObjectName("dim")
        self._empty_label.setVisible(False)
        layout.addWidget(self._empty_label)
        self.failure = failure_label(layout)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(
            [tr("ui.col.severity"), tr("ui.col.where"), tr("ui.col.message")]
        )
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.itemDoubleClicked.connect(self._on_double_clicked)
        layout.addWidget(self.tree, 1)

    def set_results(self, project: Project, results: Results, dark: bool) -> None:
        """Fill the flag tree from the current results."""
        self.failure.hide()
        self.tree.clear()
        ordered = sorted(
            results.flags,
            key=lambda flag: self._SEVERITY_ORDER.get(flag.severity, 3),
        )
        self._flags = list(ordered)

        palette = theme("dark" if dark else "light")
        brushes = {
            "error": QBrush(QColor(palette["qc_err"])),
            "warning": QBrush(QColor(palette["qc_warn"])),
        }

        for index, flag in enumerate(ordered):
            item = QTreeWidgetItem(
                [
                    tr(f"ui.severity.{flag.severity}"),
                    self._where(flag),
                    flag_text(flag),
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, index)
            brush = brushes.get(flag.severity)
            if brush is not None:
                for column in range(3):
                    item.setBackground(column, brush)
            self.tree.addTopLevelItem(item)

        self._empty_label.setVisible(not ordered)

    def show_failure(self, text: str) -> None:
        self.tree.clear()
        self._flags = []
        self._empty_label.hide()
        self.failure.setText(text)
        self.failure.show()

    def item_for_flag(self, code: str) -> QTreeWidgetItem | None:
        """Return the first tree item carrying the given flag code."""
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            if item is None:
                continue
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data is None:
                continue
            try:
                flag = self._flags[int(data)]
            except (IndexError, TypeError, ValueError):
                continue
            if flag.code == code:
                return item
        return None

    @staticmethod
    def _where(flag: Flag) -> str:
        parts: list[str] = []
        if flag.run_id:
            parts.append(flag.run_id)
        if flag.coords:
            parts.append(", ".join(flag.coords))
        if flag.target:
            parts.append(flag.target)
        if flag.sample:
            parts.append(flag.sample)
        return " ".join(parts)

    def _on_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            return
        try:
            flag = self._flags[int(data)]
        except (IndexError, TypeError, ValueError):
            return
        if flag.run_id and flag.coords:
            self.locate.emit(flag.run_id, flag.coords[0])

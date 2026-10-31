"""Editable table of all reactions with filter and paste-from-Excel."""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractItemModel,
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QStyledItemDelegate,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from i18n import tr
from qpcr_core.editing import (
    apply_sample_table,
    assign_sample,
    set_excluded,
    set_group,
    set_quantity,
    set_role,
)
from qpcr_core.importers.textio import parse_number
from qpcr_core.models import ROLES
from ui.editor import ProjectEditor

COLUMNS = ("run", "well", "sample", "group", "target", "role", "cq", "quantity", "excluded")
_COL = {name: index for index, name in enumerate(COLUMNS)}
SORT_ROLE = Qt.ItemDataRole.UserRole
_FILTER_COLUMNS = (_COL["run"], _COL["well"], _COL["sample"], _COL["target"])


class _FilterProxy(QSortFilterProxyModel):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._needle = ""

    def set_text(self, text: str) -> None:
        if hasattr(self, "beginFilterChange"):  # Qt >= 6.10
            self.beginFilterChange()
            self._needle = text.strip().lower()
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            self._needle = text.strip().lower()
            self.invalidateRowsFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if not self._needle:
            return True
        model = self.sourceModel()
        if model is None:
            return True
        for column in _FILTER_COLUMNS:
            index = model.index(source_row, column, source_parent)
            value = model.data(index, Qt.ItemDataRole.DisplayRole)
            if value is not None and self._needle in str(value).lower():
                return True
        return False


class RoleDelegate(QStyledItemDelegate):
    def createEditor(self, parent: QWidget, option: object, index: QModelIndex) -> QWidget:
        combo = QComboBox(parent)
        for role in ROLES:
            combo.addItem(tr(f"ui.role.{role}"), role)
        return combo

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:
        if not isinstance(editor, QComboBox):
            return
        role = index.data(Qt.ItemDataRole.EditRole) or "unknown"
        position = editor.findData(role)
        editor.setCurrentIndex(position if position >= 0 else 0)

    def setModelData(
        self, editor: QWidget, model: QAbstractItemModel, index: QModelIndex
    ) -> None:
        if isinstance(editor, QComboBox):
            model.setData(index, editor.currentData(), Qt.ItemDataRole.EditRole)


class ReactionModel(QAbstractTableModel):
    def __init__(self, editor: ProjectEditor) -> None:
        super().__init__()
        self.editor = editor
        self._rows: list[tuple[str, str, int]] = []
        self._edits = {
            "sample": self._edit_sample,
            "group": self._edit_group,
            "role": self._edit_role,
            "quantity": self._edit_quantity,
        }
        editor.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        self.beginResetModel()
        self._rows = [
            (run.id, well.coord, reaction_index)
            for run in self.editor.project.runs
            for well in run.wells.values()
            for reaction_index in range(len(well.reactions))
        ]
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
            and 0 <= section < len(COLUMNS)
        ):
            return tr(f"ui.col.{COLUMNS[section]}")
        return super().headerData(section, orientation, role)

    def _locate(self, row: int):
        run_id, coord, reaction_index = self._rows[row]
        run = self.editor.project.run(run_id)
        well = run.wells[coord]
        return run, well, well.reactions[reaction_index]

    def _group(self, well) -> str:
        if not well.sample:
            return ""
        sample = self.editor.project.samples.get(well.sample)
        return sample.group if sample is not None else ""

    def data(
        self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if not index.isValid():
            return None
        try:
            run, well, reaction = self._locate(index.row())
        except (IndexError, KeyError):
            return None

        column = COLUMNS[index.column()]
        if role == Qt.ItemDataRole.CheckStateRole and column == "excluded":
            return Qt.CheckState.Checked if reaction.excluded else Qt.CheckState.Unchecked
        if role == SORT_ROLE and column in ("cq", "quantity"):
            value = getattr(reaction, column)
            return float("inf") if value is None else value
        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole, SORT_ROLE):
            return None

        if column == "run":
            return run.id
        if column == "well":
            return well.coord
        if column == "sample":
            return well.sample or ""
        if column == "group":
            return self._group(well)
        if column == "target":
            return reaction.target
        if column == "role":
            if role == Qt.ItemDataRole.DisplayRole:
                return tr(f"ui.role.{reaction.role}")
            return reaction.role
        if column == "cq":
            return f"{reaction.cq:.2f}" if reaction.cq is not None else "—"
        if column == "quantity":
            return f"{reaction.quantity:g}" if reaction.quantity is not None else ""
        if column == "excluded":
            return "" if role == Qt.ItemDataRole.DisplayRole else reaction.excluded
        return None

    def setData(
        self,
        index: QModelIndex,
        value: object,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        if not index.isValid():
            return False
        try:
            run, well, reaction = self._locate(index.row())
        except (IndexError, KeyError):
            return False

        column = COLUMNS[index.column()]
        if role == Qt.ItemDataRole.CheckStateRole and column == "excluded":
            try:
                checked = Qt.CheckState(value) == Qt.CheckState.Checked
            except (TypeError, ValueError):
                return False
            self.editor.apply(
                set_excluded,
                run.id,
                well.coord,
                reaction.target,
                checked,
                "manual",
            )
            return True

        if role != Qt.ItemDataRole.EditRole:
            return False
        edit = self._edits.get(column)
        if edit is None:
            return False
        return edit(run, well, reaction, value)

    def _edit_sample(self, run, well, reaction, value: object) -> bool:
        self.editor.apply(
            assign_sample, run.id, [well.coord], "" if value is None else str(value)
        )
        return True

    def _edit_group(self, run, well, reaction, value: object) -> bool:
        if not well.sample:
            return False
        self.editor.apply(set_group, well.sample, "" if value is None else str(value))
        return True

    def _edit_role(self, run, well, reaction, value: object) -> bool:
        self.editor.apply(
            set_role,
            run.id,
            [well.coord],
            "" if value is None else str(value),
            target=reaction.target,
        )
        return True

    def _edit_quantity(self, run, well, reaction, value: object) -> bool:
        if value is None or (isinstance(value, str) and not value.strip()):
            quantity = None
        else:
            try:
                quantity = parse_number(str(value))
            except (TypeError, ValueError):
                return False
            if quantity is None:
                return False
        self.editor.apply(
            set_quantity,
            run.id,
            [well.coord],
            quantity,
            target=reaction.target,
        )
        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        column = COLUMNS[index.column()]
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if column in ("sample", "group", "role", "quantity"):
            flags |= Qt.ItemFlag.ItemIsEditable
        if column == "excluded":
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags


class DataTable(QWidget):
    def __init__(self, editor: ProjectEditor) -> None:
        super().__init__()
        self.editor = editor
        self.model = ReactionModel(editor)
        self.proxy = _FilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setDynamicSortFilter(True)
        self.proxy.setSortRole(SORT_ROLE)

        self.filter = QLineEdit(self)
        self.filter.setPlaceholderText(tr("ui.filter"))
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self.set_filter)

        hint = QLabel(tr("ui.paste_hint"), self)
        hint.setStyleSheet("color: gray;")
        font = hint.font()
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1.0))
        hint.setFont(font)

        self.table = QTableView(self)
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setItemDelegateForColumn(_COL["role"], RoleDelegate(self.table))
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.addWidget(self.filter)
        layout.addWidget(hint)
        layout.addWidget(self.table, 1)

        self._paste_shortcut = QShortcut(
            QKeySequence(QKeySequence.StandardKey.Paste), self.table
        )
        self._paste_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._paste_shortcut.activated.connect(self._paste_clipboard)

    def refresh(self) -> None:
        self.model.refresh()

    def set_filter(self, text: str) -> None:
        self.proxy.set_text(text)

    def visible_row_count(self) -> int:
        return self.proxy.rowCount()

    def paste_sample_table(self, text: str) -> int:
        rows = [line.split("\t") for line in text.splitlines()]
        return int(self.editor.apply(apply_sample_table, rows))

    def _paste_clipboard(self) -> None:
        self.paste_sample_table(QApplication.clipboard().text())

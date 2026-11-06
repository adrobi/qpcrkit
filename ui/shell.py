"""The window frame: navigation on the left, top bar with chips, the hint line."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from i18n import tr
from qpcr_core.editing import set_target_kind, update_settings
from qpcr_core.hints import Hint
from qpcr_core.models import Project
from ui.editor import ProjectEditor
from ui.side_panels import ProjectTree
from ui.theme import LIGHT, DARK, icon

PAGES = (
    ("plate", "grid-3x3"),
    ("data", "table-2"),
    ("std", "chart-scatter"),
    ("expr", "chart-column"),
    ("qc", "shield-check"),
)


class NavRail(QWidget):
    page_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("navRail")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedWidth(210)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(2)
        self.buttons: dict[str, QPushButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for name, _icon in PAGES:
            button = QPushButton(tr(f"tab.{name}"))
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setIconSize(QSize(16, 16))
            button.clicked.connect(lambda _checked=False, n=name: self.page_selected.emit(n))
            group.addButton(button)
            layout.addWidget(button)
            self.buttons[name] = button
        self.buttons["plate"].setChecked(True)
        layout.addSpacing(10)
        self.tree = ProjectTree()
        layout.addWidget(self.tree, 1)
        self.set_theme(False)

    def set_page(self, name: str) -> None:
        self.buttons[name].setChecked(True)

    def set_qc_count(self, errors: int, warnings: int) -> None:
        count = errors + warnings
        title = tr("tab.qc")
        self.buttons["qc"].setText(f"{title} · {count}" if count else title)
        self.buttons["qc"].setToolTip(tr("ui.qc_count", errors=errors, warnings=warnings) if count else "")

    def set_theme(self, dark: bool) -> None:
        t = DARK if dark else LIGHT
        for name, icon_name in PAGES:
            self.buttons[name].setIcon(icon(icon_name, t["dim"]))
        self.tree.set_theme(dark)


class TopBar(QWidget):
    settings_requested = Signal()

    def __init__(self, editor: ProjectEditor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.editor = editor
        self.setObjectName("topBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 10, 8)
        self.name_label = QLabel()
        self.name_label.setObjectName("projectName")
        layout.addWidget(self.name_label)
        layout.addSpacing(16)
        self.ref_chip = self._chip()
        self.control_chip = self._chip()
        layout.addWidget(self.ref_chip)
        layout.addWidget(self.control_chip)
        layout.addStretch(1)
        self.settings_button = QToolButton()
        self.settings_button.setText(tr("ui.analysis_settings"))
        self.settings_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.settings_button.clicked.connect(lambda: self.settings_requested.emit())
        layout.addWidget(self.settings_button)
        self.set_theme(False)

    @staticmethod
    def _chip() -> QToolButton:
        chip = QToolButton()
        chip.setObjectName("chip")
        chip.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        chip.setMenu(QMenu(chip))
        return chip

    def refresh(self, project: Project, path: Path | None) -> None:
        self.name_label.setText(path.name if path else tr("ui.untitled"))
        self._refresh_references(project)
        self._refresh_control(project)

    def _refresh_references(self, project: Project) -> None:
        menu = self.ref_chip.menu()
        menu.clear()
        chosen = []
        for name in sorted(project.targets):
            is_ref = project.targets[name].kind == "reference"
            action = QAction(name, menu, checkable=True, checked=is_ref)
            action.triggered.connect(lambda on, n=name: self.editor.apply(set_target_kind, n, "reference" if on else "target"))
            menu.addAction(action)
            if is_ref:
                chosen.append(name)
        if not project.targets:
            menu.addAction(QAction(tr("ui.chip.no_targets"), menu, enabled=False))
        value = ", ".join(chosen) if chosen else tr("ui.chip.not_set")
        self.ref_chip.setText(tr("ui.chip.reference", value=value))
        self._mark(self.ref_chip, not chosen)

    def _refresh_control(self, project: Project) -> None:
        s = project.settings
        menu = self.control_chip.menu()
        menu.clear()
        groups = sorted({x.group.strip() for x in project.samples.values() if (x.group or "").strip()})
        for group in groups:
            action = QAction(group, menu, checkable=True, checked=group == s.control_group)
            action.triggered.connect(lambda _on, g=group: self.editor.apply(update_settings, control_group=g))
            menu.addAction(action)
        if not groups:
            menu.addAction(QAction(tr("ui.chip.no_groups"), menu, enabled=False))
        value = s.control_group or s.calibrator_sample or tr("ui.chip.not_set")
        self.control_chip.setText(tr("ui.chip.control", value=value))
        self._mark(self.control_chip, not (s.control_group or s.calibrator_sample))

    @staticmethod
    def _mark(chip: QToolButton, missing: bool) -> None:
        if chip.property("missing") != missing:
            chip.setProperty("missing", missing)
            chip.style().unpolish(chip)
            chip.style().polish(chip)

    def set_theme(self, dark: bool) -> None:
        self.settings_button.setIcon(icon("settings-2", (DARK if dark else LIGHT)["dim"]))


class HintBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("hintBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        self.label = QLabel()
        layout.addWidget(self.label, 1)
        self.hide()

    def set_hint(self, hint: Hint | None) -> None:
        if hint is None:
            self.hide()
            return
        self.label.setText(tr(hint.key, **hint.params))
        self.show()

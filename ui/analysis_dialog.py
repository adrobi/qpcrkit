"""Analysis settings: a window beside the workspace, changes apply at once."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QWidget

from i18n import tr
from ui.editor import ProjectEditor
from ui.side_panels import SettingsPanel


class AnalysisDialog(QDialog):
    def __init__(self, editor: ProjectEditor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle(tr("ui.analysis_settings"))
        self.resize(460, 620)
        self.panel = SettingsPanel(editor)
        layout = QVBoxLayout(self)
        layout.addWidget(self.panel, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def open_settings(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def dispose(self) -> None:
        """Before a rebuild: the panel must stop listening at once, deleteLater comes too late."""
        self.editor.changed.disconnect(self.panel.refresh)
        self.close()
        self.deleteLater()

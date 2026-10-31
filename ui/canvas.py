"""A slot for a matplotlib Figure inside Qt layouts."""

from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class FigureCanvas(QWidget):
    def __init__(self, placeholder: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._placeholder = QLabel(placeholder)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setObjectName("dim")
        self._layout.addWidget(self._placeholder)
        self._canvas: FigureCanvasQTAgg | None = None

    def set_placeholder(self, text: str) -> None:
        self._placeholder.setText(text)

    def set_figure(self, fig: Figure | None) -> None:
        if self._canvas is not None:
            self._layout.removeWidget(self._canvas)
            self._canvas.deleteLater()
            self._canvas = None
        self._placeholder.setVisible(fig is None)
        if fig is not None:
            self._canvas = FigureCanvasQTAgg(fig)
            self._layout.addWidget(self._canvas)
            self._canvas.draw_idle()

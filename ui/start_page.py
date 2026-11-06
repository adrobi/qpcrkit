"""What an empty project shows: where to drop files, and how to try the program."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from i18n import tr
from ui.theme import icon, theme


class StartPage(QWidget):
    add_requested = Signal()
    open_requested = Signal()
    demo_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel(tr("start.title"))
        title.setObjectName("projectName")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note = QLabel(tr("start.note"))
        note.setObjectName("dim")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setWordWrap(True)

        self.add_button = QPushButton(tr("start.add"))
        self.add_button.setObjectName("primaryBtn")
        self.open_button = QPushButton(tr("start.open"))
        self.demo_button = QPushButton(tr("start.demo"))
        self.add_button.clicked.connect(lambda: self.add_requested.emit())
        self.open_button.clicked.connect(lambda: self.open_requested.emit())
        self.demo_button.clicked.connect(lambda: self.demo_requested.emit())
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for button in (self.add_button, self.open_button, self.demo_button):
            buttons.addWidget(button)
        buttons.addStretch(1)

        card = QFrame()
        card.setObjectName("startCard")
        card.setFixedSize(560, 300)
        inner = QVBoxLayout(card)
        inner.setContentsMargins(28, 24, 28, 24)
        inner.addStretch(1)
        inner.addWidget(self.picture)
        inner.addSpacing(10)
        inner.addWidget(title)
        inner.addWidget(note)
        inner.addSpacing(16)
        inner.addLayout(buttons)
        inner.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(2)
        self.set_theme(False)

    def set_theme(self, dark: bool) -> None:
        t = theme("dark" if dark else "light")
        self.picture.setPixmap(icon("upload", t["accent"]).pixmap(QSize(40, 40)))
        self.add_button.setIcon(icon("plus", t["on_accent"]))
        self.open_button.setIcon(icon("folder-open", t["dim"]))
        self.demo_button.setIcon(icon("flask-conical", t["dim"]))

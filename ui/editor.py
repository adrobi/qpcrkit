"""The single owner of the open project: every edit goes through apply() and is undoable."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from qpcr_core.editing import EditHistory
from qpcr_core.models import Project


class ProjectEditor(QObject):
    changed = Signal()

    def __init__(self, project: Project | None = None) -> None:
        super().__init__()
        self._project = project or Project()
        self._history = EditHistory()
        self._dirty = False
        self.path: Path | None = None

    @property
    def project(self) -> Project:
        return self._project

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def can_undo(self) -> bool:
        return self._history.can_undo

    @property
    def can_redo(self) -> bool:
        return self._history.can_redo

    def set_project(self, project: Project, path: Path | None = None) -> None:
        self._project = project
        self._history = EditHistory()
        self._dirty = False
        self.path = Path(path) if path else None
        self.changed.emit()

    def apply(self, fn: Callable[..., object], *args, **kwargs) -> object:
        self._history.record(self._project)
        result = fn(self._project, *args, **kwargs)
        self._dirty = True
        self.changed.emit()
        return result

    def undo(self) -> bool:
        return self._swap(self._history.undo(self._project))

    def redo(self) -> bool:
        return self._swap(self._history.redo(self._project))

    def _swap(self, project: Project | None) -> bool:
        if project is None:
            return False
        self._project = project
        self._dirty = True
        self.changed.emit()
        return True

    def mark_saved(self, path: Path) -> None:
        self.path = Path(path)
        self._dirty = False
        self.changed.emit()

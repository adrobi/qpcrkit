"""Last-resort error dialog: show what happened and let the user copy a report for an issue."""

from __future__ import annotations

import platform
import sys
import traceback
from collections.abc import Callable

import qpcr_core
from i18n import tr


def format_report(exc_info) -> str:
    import PySide6

    lines = traceback.format_exception(*exc_info)
    header = (
        f"qpcrkit {qpcr_core.__version__} · Python {platform.python_version()} · "
        f"PySide6 {PySide6.__version__} · {platform.platform()}"
    )
    return header + "\n\n" + "".join(lines)


def install_excepthook(parent_getter: Callable[[], object]) -> None:
    from PySide6.QtWidgets import QApplication, QMessageBox

    def hook(exc_type, exc, tb) -> None:
        report = format_report((exc_type, exc, tb))
        sys.__stderr__.write(report)
        box = QMessageBox(QMessageBox.Icon.Critical, "qpcrkit", tr("ui.crash_text", error=exc), parent=parent_getter())
        box.setDetailedText(report)
        copy = box.addButton(tr("ui.copy_report"), QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() is copy:
            QApplication.clipboard().setText(report)

    sys.excepthook = hook

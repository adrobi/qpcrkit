import sys

import qpcr_core
from ui.errors import format_report


def test_format_report():
    try:
        raise ValueError("bad data")
    except ValueError:
        text = format_report(sys.exc_info())
    assert "ValueError" in text and "bad data" in text
    assert qpcr_core.__version__ in text and "Python" in text


def test_hook_without_stderr(qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from ui.errors import install_excepthook

    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self.detailedText()) or 0)
    monkeypatch.setattr(sys, "__stderr__", None)
    old = sys.excepthook
    try:
        install_excepthook(lambda: None)
        try:
            raise ValueError("windowed build")
        except ValueError:
            sys.excepthook(*sys.exc_info())
    finally:
        sys.excepthook = old
    assert shown and "windowed build" in shown[0]

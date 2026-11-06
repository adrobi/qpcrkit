import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def no_app_stylesheet(qapp):
    """The application stylesheet set by other tests would apply over a widget's own."""
    old = qapp.styleSheet()
    qapp.setStyleSheet("")
    yield qapp
    qapp.setStyleSheet(old)


@pytest.fixture(autouse=True)
def no_config_writes(monkeypatch):
    monkeypatch.setattr("qpcr_core.config.save_config", lambda *a, **k: None)
    import importlib.util
    import sys

    if "ui.main_window" in sys.modules or importlib.util.find_spec("ui.main_window"):
        monkeypatch.setattr("ui.main_window.save_config", lambda *a, **k: None, raising=False)


_ROOT = Path(__file__).resolve().parent.parent
RUN1, RUN2 = _ROOT / "examples" / "demo_run1.csv", _ROOT / "examples" / "demo_run2.csv"


@pytest.fixture
def win(qapp):
    from qpcr_core.config import AppConfig
    from ui.main_window import MainWindow

    w = MainWindow(AppConfig())
    w.errors = []
    w._show_error = w.errors.append
    w.resize(1200, 800)
    yield w
    w.editor.mark_saved(Path("x"))  # no close prompt
    w.close()
    w.deleteLater()
    qapp.processEvents()


@pytest.fixture
def demo(win):
    from qpcr_core.editing import set_target_kind, update_settings

    assert win.add_run(RUN1) and win.add_run(RUN2)
    win.editor.apply(set_target_kind, "GAPDH", "reference")
    win.editor.apply(update_settings, control_group="Ctrl")
    win.recalculate_now()
    return win

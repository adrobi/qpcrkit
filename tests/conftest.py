import os

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

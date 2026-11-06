"""The start screen, dropping files on the window, the demo."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from qpcr_core.sessions import save_project
from tests.conftest import RUN1, RUN2
from tests.test_pipeline import demo_project
from ui.theme import demo_path

REAL = Path(__file__).parent / "data" / "real"
CFX_FILES = sorted(REAL.glob("2016-09-04*"))


def _mime(*urls) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([u if isinstance(u, QUrl) else QUrl.fromLocalFile(str(u)) for u in urls])
    return mime


def _drop(win, *paths) -> None:
    mime = _mime(*paths)  # the event does not own it
    event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    win.dropEvent(event)


def _enter(win, *urls) -> bool:
    mime = _mime(*urls)
    event = QDragEnterEvent(QPoint(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    event.ignore()
    win.dragEnterEvent(event)
    return event.isAccepted()


# --- start screen ---


def test_empty_window_shows_the_start_screen(win):
    assert win.is_start_shown()


def test_first_run_opens_the_plate(win):
    assert win.add_run(RUN1)
    assert not win.is_start_shown() and win.current_page() == "plate"


def test_new_project_goes_back_to_start(win):
    win.add_run(RUN1)
    win.editor.mark_saved(Path("x"))
    assert win.new_project()
    assert win.is_start_shown()


def test_undo_goes_back_and_redo_returns(win):
    win.add_run(RUN1)
    win.editor.undo()
    assert win.is_start_shown()
    win.editor.redo()
    assert not win.is_start_shown()


def test_opening_a_project_leaves_the_start(win, tmp_path):
    path = tmp_path / "p.qpcrkit.json"
    save_project(demo_project(), path)
    assert win.open_project(path)
    assert not win.is_start_shown()


def test_second_run_keeps_the_page(demo):
    demo.go_to("expr")
    demo.add_run(RUN1)
    assert demo.current_page() == "expr"


def test_start_buttons(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "_add_run_dialog", lambda: calls.append("add"))
    monkeypatch.setattr(win, "_open_dialog", lambda: calls.append("open"))
    monkeypatch.setattr(win, "open_demo", lambda: calls.append("demo"))
    win._build_ui()  # the signals are connected to the replaced methods
    win.start_page.add_button.click()
    win.start_page.open_button.click()
    win.start_page.demo_button.click()
    assert calls == ["add", "open", "demo"]


# --- dropping ---


def test_local_files_are_welcome(win, tmp_path):
    assert _enter(win, RUN1)
    assert _enter(win, tmp_path)


def test_remote_addresses_are_not(win):
    assert not _enter(win, QUrl("http://example.org/run.csv"))
    assert not _enter(win, RUN1, QUrl("http://example.org/run.csv"))


def test_drop_one_file_adds_a_run(win):
    _drop(win, RUN1)
    assert [r.source_file for r in win.editor.project.runs] and not win.is_start_shown()


def test_drop_several_files_of_one_run(win):
    _drop(win, *CFX_FILES)
    assert len(win.editor.project.runs) == 1
    assert any(r.amplification for w in win.editor.project.runs[0].wells.values() for r in w.reactions)


def test_drop_a_folder(win, tmp_path):
    import shutil

    for f in CFX_FILES:
        shutil.copy(f, tmp_path / f.name)
    _drop(win, tmp_path)
    assert len(win.editor.project.runs) == 1


def test_drop_an_unsupported_file_says_so(win, tmp_path):
    f = tmp_path / "plate.pcrd"
    f.write_bytes(b"PK\x03\x04binary")
    _drop(win, f)
    assert win.errors and win.is_start_shown()


def test_drop_a_mix_skips_the_binary_and_tells(win, tmp_path):
    f = tmp_path / "plate.pcrd"
    f.write_bytes(b"PK\x03\x04binary")
    _drop(win, RUN1, f)
    assert len(win.editor.project.runs) == 1 and not win.errors
    assert "plate.pcrd" in win.last_import_note


def test_drop_a_project_file_opens_it(win, tmp_path):
    path = tmp_path / "p.qpcrkit.json"
    save_project(demo_project(), path)
    _drop(win, path)
    assert win.editor.path == path and win.editor.project.runs


def test_drop_a_project_with_unsaved_changes_asks(win, tmp_path, monkeypatch):
    path = tmp_path / "p.qpcrkit.json"
    save_project(demo_project(), path)
    win.add_run(RUN2)
    before = win.editor.project
    monkeypatch.setattr(win, "_ask_save", lambda: "cancel")
    _drop(win, path)
    assert win.editor.project is before


# --- demo ---


def test_demo_is_small_enough():
    assert demo_path().stat().st_size <= 300_000


def test_demo_opens_with_curves_and_results(win):
    assert win.open_demo()
    assert not win.is_start_shown()
    assert win.editor.path is None and not win.editor.dirty
    assert win.results.groups and win.results.curves
    assert win.curves.line_count() > 0
    assert win.hint_bar.isHidden()


def test_demo_asks_before_dropping_unsaved_work(win, monkeypatch):
    win.add_run(RUN1)
    before = win.editor.project
    monkeypatch.setattr(win, "_ask_save", lambda: "cancel")
    assert win.open_demo() is False
    assert win.editor.project is before


@pytest.mark.parametrize("target", ["GAPDH", "IL6"])
def test_demo_curves_agree_with_its_cq(win, target):
    win.open_demo()
    project = win.editor.project
    for run in project.runs:
        diffs = []
        for coord, well in run.wells.items():
            for r in well.reactions:
                result = win.results.curves.get((run.id, coord, r.target, r.fluor))
                if r.target == target and r.cq is not None and result and result.cq_calc is not None:
                    diffs.append(result.cq_calc - r.cq)
        assert len(diffs) >= 5
        assert np.std(diffs, ddof=1) <= 0.15


def test_demo_has_melt_curves(win):
    win.open_demo()
    win.curves.mode_combo.setCurrentIndex(win.curves.mode_combo.findData("melt"))
    assert win.curves.line_count() > 0
    tms = [r.tms[0] for r in win.results.curves.values() if r.tms]
    assert tms

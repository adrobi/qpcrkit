from pathlib import Path

import pytest

from qpcr_core.config import AppConfig
from qpcr_core.editing import set_target_kind, update_settings
from qpcr_core.importers.generic_csv import ColumnMapping

ROOT = Path(__file__).resolve().parent.parent
RUN1, RUN2 = ROOT / "examples" / "demo_run1.csv", ROOT / "examples" / "demo_run2.csv"


@pytest.fixture
def win(qapp):
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
    assert win.add_run(RUN1) and win.add_run(RUN2)
    win.editor.apply(set_target_kind, "GAPDH", "reference")
    win.editor.apply(update_settings, control_group="Ctrl")
    win.recalculate_now()
    return win


def test_entry_points():
    from ui.main_window import MainWindow, run

    assert callable(run) and MainWindow is not None


def test_demo_renders_all_tabs_themes_languages(demo):
    assert demo.results is not None and demo.results.groups
    for dark in (True, False):
        demo.apply_theme(dark)
        for lang in ("en", "ru"):
            demo.set_language(lang)
            for i in range(demo.tabs.count()):
                demo.tabs.setCurrentIndex(i)
                assert not demo.grab().isNull()


def test_exclude_from_plate_and_undo(demo):
    demo.select_run("R1")
    before = demo.results.mean_cq[("Ctrl-1", "GAPDH")]
    demo.plate.exclude_toggled.emit("A1")
    demo.recalculate_now()
    after = demo.results.mean_cq[("Ctrl-1", "GAPDH")]
    assert after != before
    assert demo.editor.undo()
    demo.recalculate_now()
    assert demo.results.mean_cq[("Ctrl-1", "GAPDH")] == pytest.approx(before)


def test_plate_actions_assign_group(demo):
    demo.select_run("R1")
    demo.plate.select_coords(["A1", "A2"])
    demo.apply_sample_to_selection("NewSample")
    demo.apply_group_to_selection("NewGroup")
    p = demo.editor.project
    assert p.run("R1").wells["A2"].sample == "NewSample"
    assert p.samples["NewSample"].group == "NewGroup"
    assert demo.plate.selected_coords() == ["A1", "A2"]  # selection survives edits


def test_analysis_error_keeps_window(demo, monkeypatch):
    old = demo.results

    def boom(project):
        raise RuntimeError("kaboom")

    monkeypatch.setattr("ui.main_window.analyze", boom)
    demo.recalculate_now()
    assert demo.results is old
    assert "kaboom" in demo.statusBar().currentMessage()


def test_unsaved_cancel_keeps_project(demo, tmp_path):
    assert demo.editor.dirty
    demo._ask_save = lambda: "cancel"
    other = tmp_path / "o.qpcrkit.json"
    other.write_text("{}", encoding="utf-8")
    runs = len(demo.editor.project.runs)
    assert demo.open_project(other) is False
    assert len(demo.editor.project.runs) == runs
    from PySide6.QtGui import QCloseEvent

    ev = QCloseEvent()
    demo.closeEvent(ev)
    assert not ev.isAccepted()


def test_corrupt_session(demo, tmp_path):
    demo.editor.mark_saved(tmp_path / "cur.qpcrkit.json")
    bad = tmp_path / "bad.qpcrkit.json"
    bad.write_text("{nope", encoding="utf-8")
    runs = len(demo.editor.project.runs)
    assert demo.open_project(bad) is False
    assert demo.errors and "bad.qpcrkit.json" in demo.errors[-1]
    assert len(demo.editor.project.runs) == runs


def test_save_and_reopen(demo, tmp_path):
    path = tmp_path / "exp.qpcrkit.json"
    assert demo.save_project(path)
    assert not demo.editor.dirty
    assert demo.open_project(path)
    assert len(demo.editor.project.runs) == 2 and demo.results.groups


def test_unknown_format_wizard(win, tmp_path):
    g = tmp_path / "g.csv"
    g.write_text("Pos,Gene,Ct\nA1,IL6,20\n", encoding="utf-8")
    win._run_wizard = lambda rows: None
    assert win.add_run(g) is False
    assert win.editor.project.runs == []
    win._run_wizard = lambda rows: ColumnMapping(well="Pos", target="Gene", cq="Ct")
    assert win.add_run(g) is True
    assert len(win.editor.project.runs) == 1


def test_export_permission_error(demo, tmp_path, monkeypatch):
    def locked(*a, **k):
        raise PermissionError("file is open in Excel")

    monkeypatch.setattr("ui.main_window.export_xlsx", locked)
    assert demo.export("xlsx", tmp_path / "r.xlsx") is False
    assert demo.errors and "Excel" in demo.errors[-1]


def test_exports(demo, tmp_path):
    for kind, name in (("xlsx", "r.xlsx"), ("csv", "r.csv"), ("html", "r.html")):
        assert demo.export(kind, tmp_path / name)
        assert (tmp_path / name).stat().st_size > 0
    assert demo.export("figures", tmp_path / "figs")
    assert list((tmp_path / "figs").glob("*.svg"))


def test_qc_locate(demo):
    demo.tabs.setCurrentIndex(4)
    demo.qc.locate.emit("R2", "B1")
    assert demo.tabs.currentIndex() == 0
    assert demo.current_run_id == "R2" and demo.plate.selected_coords() == ["B1"]


def test_apply_bar_keeps_role_when_not_chosen(demo):
    demo.select_run("R1")
    std = next(c for c, w in demo.editor.project.run("R1").wells.items() if w.reactions[0].role == "std")
    demo.plate.select_coords([std])
    demo.sample_edit.setText("S-std")
    demo._apply_bar()
    w = demo.editor.project.run("R1").wells[std]
    assert w.sample == "S-std" and w.reactions[0].role == "std"


def test_export_uses_pending_edits(demo, tmp_path):
    import openpyxl

    demo.select_run("R1")
    before = demo.results.mean_cq[("Ctrl-1", "GAPDH")]
    demo.plate.exclude_toggled.emit("A1")  # recalculation still pending (300 ms timer)
    assert demo.export("xlsx", tmp_path / "r.xlsx")
    assert demo.results.mean_cq[("Ctrl-1", "GAPDH")] != before
    ws = openpyxl.load_workbook(tmp_path / "r.xlsx")[openpyxl.load_workbook(tmp_path / "r.xlsx").sheetnames[4]]
    ctrl1 = next(r for r in ws.iter_rows(values_only=True) if r[0] == "Ctrl-1")
    assert ctrl1[3] == pytest.approx(demo.results.mean_cq[("Ctrl-1", "IL6")])


def test_language_switch_does_not_leak_listeners(demo):
    from PySide6.QtCore import QCoreApplication, QEvent

    from qpcr_core.editing import set_group

    def receivers():
        return demo.editor.receivers("2changed()")

    demo.set_language("en")
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    base = receivers()
    for lang in ("ru", "en", "ru"):
        demo.set_language(lang)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert receivers() == base
    demo.editor.apply(set_group, "Ctrl-1", "Ctrl")  # must not touch deleted widgets


def test_import_summary_survives_recalculation(win, tmp_path):
    f = tmp_path / "cfx.csv"
    f.write_text(RUN1.read_text(encoding="utf-8") + "99,,SYBR,IL6,Unkn,,X,,20,,,\n", encoding="utf-8")
    assert win.add_run(f)
    win.recalculate_now()
    assert "1" in win.statusBar().currentMessage() and win.last_import_note in win.statusBar().currentMessage()

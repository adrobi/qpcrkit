from pathlib import Path

import pytest

from qpcr_core.config import AppConfig
from qpcr_core.editing import set_target_kind, update_settings
from qpcr_core.importers.generic_csv import ColumnMapping
from ui.main_window import PAGE_NAMES

ROOT = Path(__file__).resolve().parent.parent
RUN1, RUN2 = ROOT / "examples" / "demo_run1.csv", ROOT / "examples" / "demo_run2.csv"


def test_entry_points():
    from ui.main_window import MainWindow, run

    assert callable(run) and MainWindow is not None


def test_demo_renders_all_tabs_themes_languages(demo):
    assert demo.results is not None and demo.results.groups
    for mode in ("dark", "light"):
        demo.apply_theme(mode)
        for lang in ("en", "ru"):
            demo.set_language(lang)
            for name in PAGE_NAMES:
                demo.go_to(name)
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
    demo.go_to("qc")
    demo.qc.locate.emit("R2", "B1")
    assert demo.current_page() == "plate"
    assert demo.current_run_id == "R2" and demo.plate.selected_coords() == ["B1"]


def test_apply_bar_keeps_role_when_not_chosen(demo):
    demo.select_run("R1")
    std = next(c for c, w in demo.editor.project.run("R1").wells.items() if w.reactions[0].role == "std")
    demo.plate.select_coords([std])
    demo.selection.sample_edit.setText("S-std")
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


def test_app_icon(qapp):
    from ui.theme import app_icon

    assert not app_icon().isNull()


def test_qt_dialogs_follow_language(qapp):
    from PySide6.QtCore import QCoreApplication

    from ui.main_window import install_qt_translator

    install_qt_translator("ru")
    assert QCoreApplication.translate("QPlatformTheme", "Cancel") == "Отмена"
    install_qt_translator("en")
    assert QCoreApplication.translate("QPlatformTheme", "Cancel") == "Cancel"


def test_unsaved_dialog_buttons_translated(win):
    import i18n

    i18n.set_language("ru")
    box, buttons = win._unsaved_box()
    assert sorted(b.text() for b in buttons) == sorted(["Сохранить", "Не сохранять", "Отмена"])
    box.deleteLater()


def test_auto_theme_follows_system(win):
    from PySide6.QtCore import Qt

    win.apply_theme("auto", save=False)
    win._on_scheme_changed(Qt.ColorScheme.Dark)
    assert win.dark is True
    win._on_scheme_changed(Qt.ColorScheme.Light)
    assert win.dark is False
    win.apply_theme("light", save=False)
    win._on_scheme_changed(Qt.ColorScheme.Dark)
    assert win.dark is False


def test_app_uses_fusion(no_app_stylesheet):
    from ui.main_window import setup_app

    setup_app(no_app_stylesheet)
    assert no_app_stylesheet.style().objectName().lower() == "fusion"


def test_add_several_files_at_once(win):
    assert win.add_run([RUN1, RUN2])
    assert [r.id for r in win.editor.project.runs] == ["R1", "R2"]
    assert win.editor.undo() and win.editor.project.runs == []
    assert win.add_run(RUN1) and win.add_run(RUN2)
    assert [r.id for r in win.editor.project.runs] == ["R1", "R2"]


def test_binary_file_message(win, tmp_path):
    p = tmp_path / "x.pcrd"
    p.write_bytes(b"PK\x03\x04\x00\x00")
    assert win.add_run(p) is False
    assert win.errors and "x.pcrd" in win.errors[-1]


REAL = ROOT / "tests" / "data" / "real"


def _unnamed(win):
    cq = next(REAL.glob("2016-09-04 gapdh*Cq Results*"))
    assert win.add_run(cq)
    return win


def test_target_field_assigns_target(win):
    _unnamed(win)
    win.plate.select_coords(["A1", "A2"])
    win.selection.target_edit.setText("GAPDH")
    win._apply_bar()
    wells = win.editor.project.run("R1").wells
    assert wells["A1"].reactions[0].target == "GAPDH" and wells["A3"].reactions[0].target == "SYBR"
    assert win.editor.undo()
    assert win.editor.project.run("R1").wells["A1"].reactions[0].target == "SYBR"


def test_fill_series_from_selection(win):
    _unnamed(win)
    win.plate.select_coords(["A1", "A2", "A3", "A4"])
    win.fill_series_selected("Ctrl-", 2)
    wells = win.editor.project.run("R1").wells
    assert [wells[c].sample for c in ("A1", "A2", "A3", "A4")] == ["Ctrl-1", "Ctrl-1", "Ctrl-2", "Ctrl-2"]


def test_paste_plate_map(win):
    _unnamed(win)
    assert win.paste_plate_map("s1\ts2\n\ts3\n") == 3
    wells = win.editor.project.run("R1").wells
    assert (wells["A1"].sample, wells["A2"].sample, wells["B2"].sample) == ("s1", "s2", "s3")


def test_group_without_samples_explains(win):
    _unnamed(win)
    win.plate.select_coords(["A1"])
    win.selection.group_edit.setText("Ctrl")
    before = win.editor.dirty, len(win.editor.project.samples)
    win.editor.mark_saved(Path("x"))
    win._apply_bar()
    assert not win.editor.dirty and len(win.editor.project.samples) == before[1]
    assert win.statusBar().currentMessage() == tr_key("ui.group_needs_sample")


def tr_key(key):
    from i18n import tr

    return tr(key)


def test_suggestions_applied_after_confirmation(win):
    asked = []
    win._ask_suggestions = lambda refs, calibrator: asked.append((refs, calibrator)) or True
    assert win.add_run(REAL / "appbio_quantstudio_example10.xlsx")
    assert asked == [(["RefGene"], "Sample_1")]
    p = win.editor.project
    assert p.targets["RefGene"].kind == "reference" and p.settings.calibrator_sample == "Sample_1"


def test_suggestions_can_be_declined(win):
    win._ask_suggestions = lambda refs, calibrator: False
    assert win.add_run(REAL / "appbio_quantstudio_example10.xlsx")
    assert win.editor.project.targets["RefGene"].kind == "target"


def test_notes_are_shown(win, tmp_path):
    p = tmp_path / "en.csv"
    p.write_text(
        "Well,Fluor,Target,Content,Sample,Cq,Starting Quantity (SQ)\n"
        'A01,SYBR,IL6,Std,s,20.5,"1,250"\nA02,SYBR,IL6,Std,s,21.5,"2,500"\n',
        encoding="utf-8",
    )
    assert win.add_run(p)
    assert "1,250" in win.statusBar().currentMessage()


def test_same_language_does_not_rebuild(win, monkeypatch):
    import i18n

    win.set_language(i18n.current_language())
    calls = []
    monkeypatch.setattr(win, "_build_ui", lambda: calls.append(1))
    win.set_language(i18n.current_language())
    assert calls == []


def test_wizard_opens_for_a_folder_with_one_unknown_file(win, tmp_path):
    (tmp_path / "g.csv").write_text("Pos,Gene,Ct\nA1,IL6,20\n", encoding="utf-8")
    seen = []
    win._run_wizard = lambda rows: seen.append(rows[0]) or ColumnMapping(well="Pos", target="Gene", cq="Ct")
    assert win.add_run(tmp_path)
    assert seen == [["Pos", "Gene", "Ct"]] and len(win.editor.project.runs) == 1

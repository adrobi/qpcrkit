"""Main window: top bar, navigation with runs, hint line, and the pages of the workspace."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, Qt, QTimer, QTranslator
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import i18n
import qpcr_core
from i18n import tr
from qpcr_core.config import AppConfig, load_config, save_config
from qpcr_core.editing import (
    apply_plate_map,
    assign_sample,
    fill_series,
    set_excluded,
    set_group,
    set_quantity,
    set_role,
    set_target,
    set_target_kind,
    update_settings,
)
from qpcr_core.export import export_csv, export_html, export_xlsx
from qpcr_core.figures import expression_figure, safe_name, save_figure, std_curve_figure
from qpcr_core.hints import next_hint
from qpcr_core.importers.base import UnknownFormatError, UnsupportedFileError, add_report
from qpcr_core.importers.detect import import_files
from qpcr_core.importers.generic_csv import ColumnMapping
from qpcr_core.importers.grouping import group_files
from qpcr_core.importers.platekit import apply_layout, read_instrument_layout, read_platekit_json
from qpcr_core.importers.textio import parse_number, read_rows
from qpcr_core.models import Project
from qpcr_core.pipeline import Results, analyze
from qpcr_core.sessions import SessionError, load_project
from qpcr_core.sessions import save_project as write_project
from ui.analysis_dialog import AnalysisDialog
from ui.csv_wizard import CsvWizard
from ui.data_table import DataTable
from ui.editor import ProjectEditor
from ui.plate_view import PlateView
from ui.selection_panel import SelectionPanel
from ui.result_tabs import ExpressionTab, QcTab, StdCurveTab
from ui.shell import PAGES, HintBar, NavRail, TopBar
from ui.theme import app_icon, app_qss, resolve_dark, system_is_dark

RECALC_DELAY_MS = 300
PAGE_NAMES = tuple(name for name, _ in PAGES)
_qt_translator: QTranslator | None = None


def install_qt_translator(lang: str) -> None:
    """Translate Qt's own texts (standard dialog buttons) to match the UI language."""
    global _qt_translator
    app = QApplication.instance()
    if app is None:
        return
    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
        _qt_translator = None
    if lang == "en":
        return
    translator = QTranslator(app)
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(QLocale(lang), "qtbase", "_", path):
        app.installTranslator(translator)
        _qt_translator = translator


def _add_reports(project: Project, reports: list) -> None:
    for report in reports:
        add_report(project, report)


def _apply_layout_to_runs(project: Project, layout: dict, run_ids: list[str]) -> int:
    return sum(apply_layout(project, run_id, layout) for run_id in run_ids)


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig | None = None) -> None:
        super().__init__()
        self.config = config or load_config()
        if self.config.language in ("ru", "en"):
            i18n.set_language(self.config.language)
        install_qt_translator(i18n.current_language())
        self.setWindowIcon(app_icon())
        self.editor = ProjectEditor()
        self.results: Results | None = None
        self.current_run_id: str | None = None
        self.dark = False
        self.last_import_note = ""
        self._timer = QTimer(self, singleShot=True, interval=RECALC_DELAY_MS)
        self._timer.timeout.connect(self.recalculate_now)
        self.analysis: AnalysisDialog | None = None
        self.editor.changed.connect(self._on_project_changed)
        self.resize(1400, 860)
        self._build_ui()
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_scheme_changed)
        self.apply_theme(self.config.theme, save=False)
        self._on_project_changed()

    # --- construction -------------------------------------------------------------------------

    def _build_ui(self) -> None:
        """(Re)build every widget; also used for a language switch."""
        self.nav = NavRail()
        self.nav.page_selected.connect(self.go_to)
        self.tree = self.nav.tree
        self.tree.run_selected.connect(self.select_run)
        self.tree.add_run_requested.connect(self._add_run_dialog)
        self.top_bar = TopBar(self.editor)
        self.top_bar.settings_requested.connect(self._open_settings)
        self.hint_bar = HintBar()

        self.plate = PlateView()
        self.plate.selection_changed.connect(self._update_selection)
        self.plate.exclude_toggled.connect(self._toggle_exclusion)
        self.data = DataTable(self.editor)
        self.std = StdCurveTab()
        self.expr = ExpressionTab(self.editor)
        self.qc = QcTab()
        self.qc.locate.connect(self.locate)
        if self.analysis is not None:
            self.analysis.dispose()
        self.analysis = AnalysisDialog(self.editor, self)

        self.pages = QStackedWidget()
        self._page_widgets = {
            "plate": self._plate_page(),
            "data": self.data,
            "std": self.std,
            "expr": self.expr,
            "qc": self.qc,
        }
        for name in PAGE_NAMES:
            self.pages.addWidget(self._page_widgets[name])

        work = QWidget()
        work_layout = QVBoxLayout(work)
        work_layout.setContentsMargins(10, 8, 10, 4)
        work_layout.addWidget(self.hint_bar)
        work_layout.addWidget(self.pages, 1)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.nav)
        body.addWidget(work, 1)
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self.top_bar)
        root_layout.addLayout(body, 1)

        old = self.centralWidget()
        self.setCentralWidget(root)
        if old is not None:
            old.deleteLater()
        self._build_menus()

    def _plate_page(self) -> QWidget:
        self.selection = SelectionPanel()
        self.selection.apply_requested.connect(self._apply_bar)
        self.selection.series_requested.connect(self._fill_series_dialog)
        self.selection.exclude_requested.connect(self._set_selection_excluded)
        self.color_combo = QComboBox()
        self.color_combo.addItem(tr("ui.color.target"), "target")
        self.color_combo.addItem(tr("ui.color.role"), "role")
        self.color_combo.currentIndexChanged.connect(lambda: self.plate.set_color_mode(self.color_combo.currentData()))

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        bar.addStretch(1)
        bar.addWidget(QLabel(tr("ui.color_by")))
        bar.addWidget(self.color_combo)
        left_layout.addLayout(bar)
        left_layout.addWidget(self.plate, 1)
        left_layout.addWidget(self.selection)

        self.plate_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.plate_splitter.addWidget(left)
        return self.plate_splitter

    def _build_menus(self) -> None:
        mb = self.menuBar()
        mb.clear()
        file_menu = mb.addMenu(tr("menu.file"))
        self._action(file_menu, "act.new", self.new_project, QKeySequence.StandardKey.New)
        self._action(file_menu, "act.open", self._open_dialog, QKeySequence.StandardKey.Open)
        self.recent_menu = file_menu.addMenu(tr("act.recent"))
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        self._action(file_menu, "act.save", self.save_project, QKeySequence.StandardKey.Save)
        self._action(file_menu, "act.save_as", self._save_as_dialog, QKeySequence.StandardKey.SaveAs)
        file_menu.addSeparator()
        self._action(file_menu, "act.add_run", self._add_run_dialog)
        self._action(file_menu, "act.import_layout", self._import_layout_dialog)
        file_menu.addSeparator()
        for kind in ("xlsx", "csv", "html", "figures"):
            self._action(file_menu, f"act.export_{kind}", lambda k=kind: self._export_dialog(k))
        file_menu.addSeparator()
        self._action(file_menu, "act.exit", self.close, QKeySequence.StandardKey.Quit)

        edit_menu = mb.addMenu(tr("menu.edit"))
        self.undo_action = self._action(edit_menu, "act.undo", self.editor.undo, QKeySequence.StandardKey.Undo)
        self.redo_action = self._action(edit_menu, "act.redo", self.editor.redo, QKeySequence.StandardKey.Redo)
        self._action(edit_menu, "act.paste_map", self._paste_plate_map_from_clipboard)
        edit_menu.addSeparator()
        self._action(edit_menu, "ui.analysis_settings", self._open_settings)

        view_menu = mb.addMenu(tr("menu.view"))
        themes = QActionGroup(self)
        for mode in ("auto", "light", "dark"):
            a = self._action(view_menu, f"act.theme_{mode}", lambda m=mode: self.apply_theme(m))
            a.setCheckable(True)
            a.setChecked(self.config.theme == mode)
            themes.addAction(a)
        view_menu.addSeparator()
        langs = QActionGroup(self)
        for lang in ("ru", "en"):
            a = self._action(view_menu, f"act.lang_{lang}", lambda l=lang: self.set_language(l))
            a.setCheckable(True)
            a.setChecked(i18n.current_language() == lang)
            langs.addAction(a)

        help_menu = mb.addMenu(tr("menu.help"))
        self._action(help_menu, "act.about", self._about)

    def _action(self, menu, key: str, slot, shortcut=None) -> QAction:
        action = QAction(tr(key), self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(lambda checked=False: slot())
        menu.addAction(action)
        return action

    # --- project state -----------------------------------------------------------------------

    def _on_project_changed(self) -> None:
        project = self.editor.project
        if self.current_run_id not in {r.id for r in project.runs}:
            self.current_run_id = project.runs[0].id if project.runs else None
        self.tree.refresh(project)
        self.tree.set_current_run(self.current_run_id)
        self.top_bar.refresh(project, self.editor.path)
        self.hint_bar.set_hint(next_hint(project))
        self._show_run(keep_selection=True)
        name = self.editor.path.name if self.editor.path else tr("ui.untitled")
        self.setWindowTitle(f"qpcrkit — {name}[*]")
        self.setWindowModified(self.editor.dirty)
        self.undo_action.setEnabled(self.editor.can_undo)
        self.redo_action.setEnabled(self.editor.can_redo)
        self._timer.start()

    def _show_run(self, keep_selection: bool = False) -> None:
        coords = self.plate.selected_coords() if keep_selection else []
        run = self.editor.project.run(self.current_run_id) if self.current_run_id else None
        self.plate.set_run(run, self.editor.project)
        if coords:
            self.plate.select_coords(coords)

    def recalculate_now(self) -> None:
        self._timer.stop()
        project = self.editor.project
        try:
            results = analyze(project)
        except Exception as exc:  # a bug or odd data must not take the window down
            self.statusBar().showMessage(tr("ui.analysis_failed", error=exc))
            return
        self.results = results
        for tab in (self.std, self.expr, self.qc):
            tab.set_results(project, results, self.dark)
        self.nav.set_qc_count(len(results.flags_by_severity("error")), len(results.flags_by_severity("warning")))
        if not project.runs:
            self.statusBar().showMessage(tr("ui.no_run"))
        else:
            status = tr(
                "ui.status",
                runs=len(project.runs),
                errors=len(results.flags_by_severity("error")),
                warnings=len(results.flags_by_severity("warning")),
            )
            self.statusBar().showMessage(" · ".join(x for x in (status, self.last_import_note) if x))

    def select_run(self, run_id: str) -> None:
        self.current_run_id = run_id
        self.tree.set_current_run(run_id)
        self._show_run()

    def go_to(self, name: str) -> None:
        self.pages.setCurrentWidget(self._page_widgets[name])
        self.nav.set_page(name)

    def current_page(self) -> str:
        current = self.pages.currentWidget()
        return next(n for n, w in self._page_widgets.items() if w is current)

    def _open_settings(self) -> None:
        self.analysis.open_settings()

    def locate(self, run_id: str, coord: str) -> None:
        self.go_to("plate")
        self.select_run(run_id)
        self.plate.select_coords([coord])

    # --- plate actions -----------------------------------------------------------------------

    def _update_selection(self) -> None:
        project = self.editor.project
        run = project.run(self.current_run_id) if self.current_run_id else None
        self.selection.set_selection(project, run, self.plate.selected_coords())

    def _selection(self) -> tuple[str, list[str]] | None:
        coords = self.plate.selected_coords()
        return (self.current_run_id, coords) if self.current_run_id and coords else None

    def apply_sample_to_selection(self, sample: str) -> None:
        if sel := self._selection():
            self.editor.apply(assign_sample, sel[0], sel[1], sample)

    def apply_group_to_selection(self, group: str) -> None:
        if not (sel := self._selection()):
            return
        wells = self.editor.project.run(sel[0]).wells
        samples = sorted({wells[c].sample for c in sel[1] if wells[c].sample})
        if samples:
            self.editor.apply(lambda p: [set_group(p, s, group) for s in samples])

    def _apply_bar(self) -> None:
        """Apply whatever fields of the plate action bar are filled to the selection."""
        if not (sel := self._selection()):
            return
        run_id, coords = sel
        target = self.selection.target_edit.text().strip()
        sample, group = self.selection.sample_edit.text().strip(), self.selection.group_edit.text().strip()
        wells = self.editor.project.run(run_id).wells
        if group and not sample and not any(wells[c].sample for c in coords):
            self.statusBar().showMessage(tr("ui.group_needs_sample"))
            return
        role = self.selection.role_combo.currentData()
        qty_text = self.selection.quantity_edit.text().strip()
        quantity = parse_number(qty_text) if qty_text else None

        def edit(p: Project) -> None:
            if target:
                set_target(p, run_id, coords, target)
            if sample:
                assign_sample(p, run_id, coords, sample)
            if role:
                set_role(p, run_id, coords, role)
            if quantity is not None:
                set_quantity(p, run_id, coords, quantity)
            if group:
                for s in {p.run(run_id).wells[c].sample for c in coords} - {None}:
                    set_group(p, s, group)

        self.selection.clear_fields()
        self.editor.apply(edit)

    def fill_series_selected(self, prefix: str, replicates: int) -> None:
        if sel := self._selection():
            self.editor.apply(fill_series, sel[0], sel[1], prefix, 1, replicates)

    def _fill_series_dialog(self) -> None:
        if not self._selection():
            return
        prefix, ok = QInputDialog.getText(self, tr("ui.series"), tr("ui.series_prefix"), text="S")
        if not ok or not prefix:
            return
        reps, ok = QInputDialog.getInt(self, tr("ui.series"), tr("ui.series_replicates"), 3, 1, 96)
        if ok:
            self.fill_series_selected(prefix, reps)

    def paste_plate_map(self, text: str) -> int:
        if not self.current_run_id:
            return 0
        rows = [line.split("\t") for line in text.splitlines()]
        return int(self.editor.apply(apply_plate_map, self.current_run_id, rows))

    def _paste_plate_map_from_clipboard(self) -> None:
        self.statusBar().showMessage(tr("ui.map_pasted", n=self.paste_plate_map(QApplication.clipboard().text())))

    def _set_selection_excluded(self, excluded: bool) -> None:
        if sel := self._selection():
            self.editor.apply(lambda p: [set_excluded(p, sel[0], c, None, excluded, "manual") for c in sel[1]])

    def _toggle_exclusion(self, coord: str) -> None:
        if not self.current_run_id:
            return
        well = self.editor.project.run(self.current_run_id).wells.get(coord)
        if well is None or not well.reactions:
            return
        new = not all(r.excluded for r in well.reactions)
        self.editor.apply(set_excluded, self.current_run_id, coord, None, new, "manual")

    # --- files -------------------------------------------------------------------------------

    def _confirm_discard(self) -> bool:
        if not self.editor.dirty:
            return True
        answer = self._ask_save()
        if answer == "save":
            return self.save_project()
        return answer == "discard"

    def new_project(self) -> bool:
        if not self._confirm_discard():
            return False
        self.editor.set_project(Project())
        self.recalculate_now()
        return True

    def open_project(self, path: str | Path) -> bool:
        if not self._confirm_discard():
            return False
        try:
            project = load_project(path)
        except SessionError as exc:
            self._show_error(str(exc))
            return False
        self.last_import_note = ""
        self.editor.set_project(project, Path(path))
        self._remember(path)
        self.recalculate_now()
        return True

    def save_project(self, path: str | Path | None = None) -> bool:
        path = path or self.editor.path or self._ask_save_path(tr("ui.filter_project"), "project.qpcrkit.json")
        if not path:
            return False
        try:
            write_project(self.editor.project, path)
        except OSError as exc:
            self._show_error(tr("ui.export_failed", error=exc))
            return False
        self.editor.mark_saved(Path(path))
        self._remember(path)
        return True

    def add_run(self, paths: str | Path | list) -> bool:
        paths = paths if isinstance(paths, list) else [paths]
        used = [int(r.id[1:]) for r in self.editor.project.runs if r.id[1:].isdigit()]
        first = max(used, default=0) + 1
        try:
            try:
                reports = import_files(paths, first)
            except UnknownFormatError:
                mapping = self._run_wizard(read_rows(group_files(paths)[0][0]))
                if mapping is None:
                    return False
                reports = import_files(paths, first, mapping)
        except UnsupportedFileError as exc:
            self._show_error(tr("ui.unsupported_file", name=exc))
            return False
        except (OSError, ValueError) as exc:
            self._show_error(tr("ui.import_failed", error=exc))
            return False
        self.current_run_id = reports[0].run.id
        self.editor.apply(_add_reports, reports)
        self.last_import_note = " ".join(
            [
                tr(
                    "ui.imported",
                    imported=sum(r.imported for r in reports),
                    total=sum(r.total_rows for r in reports),
                    skipped=sum(len(r.skipped) for r in reports),
                )
            ]
            + [n for r in reports for n in r.notes]
        )
        self.statusBar().showMessage(self.last_import_note)
        self._offer_suggestions(reports)
        return True

    def _offer_suggestions(self, reports: list) -> None:
        """The file may name its reference genes and calibrator; use them if the user agrees."""
        project = self.editor.project
        refs = [t for r in reports for t in r.suggested_refs if t in project.targets]
        calibrator = next((r.suggested_calibrator for r in reports if r.suggested_calibrator in project.samples), "")
        if not refs and not calibrator:
            return
        if self._ask_suggestions(refs, calibrator):
            def apply(p: Project) -> None:
                for t in refs:
                    set_target_kind(p, t, "reference")
                if calibrator:
                    update_settings(p, calibrator_sample=calibrator)

            self.editor.apply(apply)

    def import_layout(self, path: str | Path, run_id: str | None = None) -> int:
        try:
            reader = read_platekit_json if str(path).endswith(".json") else read_instrument_layout
            layout = reader(path)
        except (OSError, ValueError) as exc:
            self._show_error(tr("ui.import_failed", error=exc))
            return 0
        run_ids = [run_id] if run_id else [r.id for r in self.editor.project.runs]
        return int(self.editor.apply(_apply_layout_to_runs, layout, run_ids))

    def export(self, kind: str, path: str | Path) -> bool:
        if self.results is None or self._timer.isActive():  # never export before pending edits are analyzed
            self.recalculate_now()
        project, results = self.editor.project, self.results
        if results is None:
            return False
        try:
            if kind == "xlsx":
                export_xlsx(project, results, path)
            elif kind == "csv":
                export_csv(results, path)
            elif kind == "html":
                export_html(project, results, path)
            elif kind == "figures":
                out = Path(path)
                out.mkdir(parents=True, exist_ok=True)
                for target in sorted({g.target for g in results.groups}):
                    fig = expression_figure(results, target, error=project.settings.error_bar)
                    save_figure(fig, out / f"expression_{safe_name(target)}.svg")
                for (run_id, target), curve in results.std_curves.items():
                    save_figure(std_curve_figure(curve), out / f"stdcurve_{safe_name(target)}_{run_id or 'pooled'}.svg")
            else:
                raise ValueError(kind)
        except OSError as exc:
            self._show_error(tr("ui.export_failed", error=exc))
            return False
        return True

    def _remember(self, path: str | Path) -> None:
        self.config.add_recent(Path(path).resolve())
        save_config(self.config)

    # --- view --------------------------------------------------------------------------------

    def apply_theme(self, mode: str, save: bool = True) -> None:
        self.config.theme = mode
        self._set_dark(resolve_dark(mode, system_is_dark()))
        if save:
            save_config(self.config)

    def _on_scheme_changed(self, scheme: Qt.ColorScheme) -> None:
        if self.config.theme == "auto":
            self._set_dark(scheme == Qt.ColorScheme.Dark)

    def _set_dark(self, dark: bool) -> None:
        self.dark = dark
        app = QApplication.instance()
        if app is not None and app.styleSheet() != app_qss(dark):  # re-setting repolishes every widget
            app.setStyleSheet(app_qss(dark))
        self.plate.set_theme(dark)
        self.nav.set_theme(dark)
        self.top_bar.set_theme(dark)
        if self.results is not None:
            for tab in (self.std, self.expr, self.qc):
                tab.set_results(self.editor.project, self.results, dark)

    def set_language(self, lang: str) -> None:
        if lang == i18n.current_language() and lang == self.config.language:
            return
        i18n.set_language(lang)
        install_qt_translator(lang)
        self.config.language = lang
        save_config(self.config)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Rebuild widgets with the new language; the project and results stay."""
        page, coords = self.current_page(), self.plate.selected_coords()
        self._build_ui()
        self.go_to(page)
        self.plate.set_theme(self.dark)
        self.nav.set_theme(self.dark)
        self.top_bar.set_theme(self.dark)
        self._on_project_changed()
        self.plate.select_coords(coords)
        self.recalculate_now()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()

    # --- dialogs (separate methods so tests can replace them) --------------------------------

    def _unsaved_box(self) -> tuple[QMessageBox, dict]:
        box = QMessageBox(QMessageBox.Icon.Question, tr("ui.unsaved_title"), tr("ui.unsaved_text"), parent=self)
        buttons = {}
        for std, key, answer in (
            (QMessageBox.StandardButton.Save, "ui.btn.save", "save"),
            (QMessageBox.StandardButton.Discard, "ui.btn.discard", "discard"),
            (QMessageBox.StandardButton.Cancel, "ui.btn.cancel", "cancel"),
        ):
            button = box.addButton(std)
            button.setText(tr(key))  # explicit, so it does not depend on Qt's own translations
            buttons[button] = answer
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        return box, buttons

    def _ask_save(self) -> str:
        box, buttons = self._unsaved_box()
        box.exec()
        return buttons.get(box.clickedButton(), "cancel")

    def _ask_open_path(self, file_filter: str) -> str | None:
        path, _ = QFileDialog.getOpenFileName(self, "", "", file_filter)
        return path or None

    def _ask_save_path(self, file_filter: str, default: str) -> str | None:
        path, _ = QFileDialog.getSaveFileName(self, "", default, file_filter)
        return path or None

    def _ask_suggestions(self, refs: list[str], calibrator: str) -> bool:
        text = tr("ui.suggest_text", refs=", ".join(refs) or "—", calibrator=calibrator or "—")
        return QMessageBox.question(self, "qpcrkit", text) == QMessageBox.StandardButton.Yes

    def _show_error(self, text: str) -> None:
        QMessageBox.critical(self, "qpcrkit", text)

    def _run_wizard(self, rows: list[list[str]]) -> ColumnMapping | None:
        wizard = CsvWizard(rows, self.config.csv_presets, self)
        if not wizard.exec():
            return None
        if preset := wizard.preset_to_save():
            self.config.csv_presets[preset[0]] = preset[1]
            save_config(self.config)
        return wizard.mapping()

    def _open_dialog(self) -> None:
        if path := self._ask_open_path(tr("ui.filter_project")):
            self.open_project(path)

    def _save_as_dialog(self) -> None:
        if path := self._ask_save_path(tr("ui.filter_project"), "project.qpcrkit.json"):
            self.save_project(path)

    def _add_run_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "", "", tr("ui.filter_tables"))
        if paths:
            self.add_run(paths)

    def _import_layout_dialog(self) -> None:
        if path := self._ask_open_path(tr("ui.filter_layout")):
            self.import_layout(path)

    def _export_dialog(self, kind: str) -> None:
        if kind == "figures":
            path = QFileDialog.getExistingDirectory(self)
        else:
            path = self._ask_save_path(f"*.{kind}", f"results.{kind}")
        if path:
            self.export(kind, path)

    def _fill_recent(self) -> None:
        self.recent_menu.clear()
        for path in self.config.recent:
            action = self.recent_menu.addAction(path)
            action.triggered.connect(lambda checked=False, p=path: self.open_project(p))

    def _about(self) -> None:
        QMessageBox.about(self, "qpcrkit", tr("ui.about_text", version=qpcr_core.__version__))


def setup_app(app: QApplication) -> None:
    app.setApplicationName("qpcrkit")
    app.setStyle("Fusion")  # the same look on every Windows version and OS theme
    app.setWindowIcon(app_icon())


def run(project: Path | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    setup_app(app)
    window = MainWindow()
    try:
        from ui.errors import install_excepthook

        install_excepthook(lambda: window)
    except ImportError:
        pass
    window.show()
    if project:
        window.open_project(project)
    return app.exec()

"""Main window: project tree | tabs (plate, data, standards, expression, QC) | settings."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import i18n
import qpcr_core
from i18n import tr
from qpcr_core.config import AppConfig, load_config, save_config
from qpcr_core.editing import assign_sample, set_excluded, set_group, set_quantity, set_role
from qpcr_core.export import export_csv, export_html, export_xlsx
from qpcr_core.figures import expression_figure, save_figure, std_curve_figure
from qpcr_core.importers.base import UnknownFormatError, add_report
from qpcr_core.importers.detect import import_file
from qpcr_core.importers.generic_csv import ColumnMapping
from qpcr_core.importers.platekit import apply_layout, read_instrument_layout, read_platekit_json
from qpcr_core.importers.textio import parse_number, read_rows
from qpcr_core.models import ROLES, Project
from qpcr_core.pipeline import Results, analyze
from qpcr_core.sessions import SessionError, load_project
from qpcr_core.sessions import save_project as write_project
from ui.csv_wizard import CsvWizard
from ui.data_table import DataTable
from ui.editor import ProjectEditor
from ui.plate_view import PlateView
from ui.result_tabs import ExpressionTab, QcTab, StdCurveTab
from ui.side_panels import ProjectTree, SettingsPanel
from ui.theme import app_qss

RECALC_DELAY_MS = 300


def _apply_layout_to_runs(project: Project, layout: dict, run_ids: list[str]) -> int:
    return sum(apply_layout(project, run_id, layout) for run_id in run_ids)


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig | None = None) -> None:
        super().__init__()
        self.config = config or load_config()
        if self.config.language in ("ru", "en"):
            i18n.set_language(self.config.language)
        self.editor = ProjectEditor()
        self.results: Results | None = None
        self.current_run_id: str | None = None
        self._timer = QTimer(self, singleShot=True, interval=RECALC_DELAY_MS)
        self._timer.timeout.connect(self.recalculate_now)
        self.editor.changed.connect(self._on_project_changed)
        self.resize(1400, 860)
        self._build_ui()
        self.apply_theme(self.config.dark, save=False)
        self._on_project_changed()

    # --- construction -------------------------------------------------------------------------

    def _build_ui(self) -> None:
        """(Re)build every widget; also used for a language switch."""
        self.tree = ProjectTree()
        self.tree.run_selected.connect(self.select_run)
        self.tree.add_run_requested.connect(self._add_run_dialog)
        self.tree.import_layout_requested.connect(self._import_layout_dialog)

        self.plate = PlateView()
        self.plate.selection_changed.connect(self._update_selection_label)
        self.plate.exclude_toggled.connect(self._toggle_exclusion)
        self.data = DataTable(self.editor)
        self.std = StdCurveTab()
        self.expr = ExpressionTab(self.editor)
        self.qc = QcTab()
        self.qc.locate.connect(self.locate)
        self.settings = SettingsPanel(self.editor)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._plate_page(), tr("tab.plate"))
        self.tabs.addTab(self.data, tr("tab.data"))
        self.tabs.addTab(self.std, tr("tab.std"))
        self.tabs.addTab(self.expr, tr("tab.expr"))
        self.tabs.addTab(self.qc, tr("tab.qc"))

        splitter = QSplitter(Qt.Orientation.Horizontal)
        for widget, stretch in ((self.tree, 1), (self.tabs, 4), (self.settings, 1)):
            splitter.addWidget(widget)
            splitter.setStretchFactor(splitter.count() - 1, stretch)
        splitter.setSizes([240, 900, 280])
        old = self.centralWidget()
        self.setCentralWidget(splitter)
        if old is not None:
            old.deleteLater()
        self._build_menus()

    def _plate_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        bar = QHBoxLayout()
        self.selection_label = QLabel()
        self.sample_edit = QLineEdit(placeholderText=tr("ui.col.sample"))
        self.group_edit = QLineEdit(placeholderText=tr("ui.col.group"))
        self.role_combo = QComboBox()
        self.role_combo.addItem(tr("ui.none"), None)  # leave roles unchanged
        for role in ROLES:
            self.role_combo.addItem(tr(f"ui.role.{role}"), role)
        self.quantity_edit = QLineEdit(placeholderText=tr("ui.col.quantity"))
        apply_btn = QPushButton(tr("ui.apply"))
        apply_btn.clicked.connect(self._apply_bar)
        exclude_btn = QPushButton(tr("ui.exclude"))
        exclude_btn.clicked.connect(lambda: self._set_selection_excluded(True))
        include_btn = QPushButton(tr("ui.include"))
        include_btn.clicked.connect(lambda: self._set_selection_excluded(False))
        self.color_combo = QComboBox()
        self.color_combo.addItem(tr("ui.color.target"), "target")
        self.color_combo.addItem(tr("ui.color.role"), "role")
        self.color_combo.currentIndexChanged.connect(lambda: self.plate.set_color_mode(self.color_combo.currentData()))
        for w in (self.selection_label, self.sample_edit, self.group_edit, self.role_combo, self.quantity_edit,
                  apply_btn, exclude_btn, include_btn, QLabel(tr("ui.color_by")), self.color_combo):
            bar.addWidget(w)
        layout.addLayout(bar)
        layout.addWidget(self.plate, 1)
        return page

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

        view_menu = mb.addMenu(tr("menu.view"))
        self.dark_action = self._action(view_menu, "act.dark", lambda: self.apply_theme(self.dark_action.isChecked()))
        self.dark_action.setCheckable(True)
        self.dark_action.setChecked(self.config.dark)
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
        dark = self.config.dark
        for tab in (self.std, self.expr, self.qc):
            tab.set_results(project, results, dark)
        if not project.runs:
            self.statusBar().showMessage(tr("ui.no_run"))
        else:
            self.statusBar().showMessage(tr(
                "ui.status",
                runs=len(project.runs),
                errors=len(results.flags_by_severity("error")),
                warnings=len(results.flags_by_severity("warning")),
            ))

    def select_run(self, run_id: str) -> None:
        self.current_run_id = run_id
        self._show_run()

    def locate(self, run_id: str, coord: str) -> None:
        self.tabs.setCurrentIndex(0)
        self.select_run(run_id)
        self.plate.select_coords([coord])

    # --- plate actions -----------------------------------------------------------------------

    def _update_selection_label(self) -> None:
        self.selection_label.setText(tr("ui.selection", n=len(self.plate.selected_coords())))

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
        sample, group = self.sample_edit.text().strip(), self.group_edit.text().strip()
        role = self.role_combo.currentData()
        qty_text = self.quantity_edit.text().strip()
        quantity = parse_number(qty_text) if qty_text else None

        def edit(p: Project) -> None:
            if sample:
                assign_sample(p, run_id, coords, sample)
            if role:
                set_role(p, run_id, coords, role)
            if quantity is not None:
                set_quantity(p, run_id, coords, quantity)
            if group:
                for s in {p.run(run_id).wells[c].sample for c in coords} - {None}:
                    set_group(p, s, group)

        self.editor.apply(edit)

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

    def add_run(self, path: str | Path) -> bool:
        ids = {r.id for r in self.editor.project.runs}
        run_id = next(f"R{i}" for i in range(1, len(ids) + 2) if f"R{i}" not in ids)
        try:
            try:
                report = import_file(path, run_id)
            except UnknownFormatError:
                mapping = self._run_wizard(read_rows(path))
                if mapping is None:
                    return False
                report = import_file(path, run_id, mapping)
        except (OSError, ValueError) as exc:
            self._show_error(tr("ui.import_failed", error=exc))
            return False
        self.current_run_id = run_id
        self.editor.apply(add_report, report)
        self.statusBar().showMessage(
            tr("ui.imported", imported=report.imported, total=report.total_rows, skipped=len(report.skipped)), 8000
        )
        return True

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
        if self.results is None:
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
                    save_figure(fig, out / f"expression_{target}.svg")
                for (run_id, target), curve in results.std_curves.items():
                    save_figure(std_curve_figure(curve), out / f"stdcurve_{target}_{run_id or 'pooled'}.svg")
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

    def apply_theme(self, dark: bool, save: bool = True) -> None:
        self.config.dark = dark
        app = QApplication.instance()
        if app is not None and app.styleSheet() != app_qss(dark):  # re-setting repolishes every widget
            app.setStyleSheet(app_qss(dark))
        self.plate.set_theme(dark)
        if save:
            save_config(self.config)
        if self.results is not None:
            for tab in (self.std, self.expr, self.qc):
                tab.set_results(self.editor.project, self.results, dark)

    def set_language(self, lang: str) -> None:
        i18n.set_language(lang)
        self.config.language = lang
        save_config(self.config)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Rebuild widgets with the new language; the project and results stay."""
        tab = self.tabs.currentIndex()
        self._build_ui()
        self.tabs.setCurrentIndex(tab)
        self.plate.set_theme(self.config.dark)
        self._on_project_changed()
        self.recalculate_now()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()

    # --- dialogs (separate methods so tests can replace them) --------------------------------

    def _ask_save(self) -> str:
        box = QMessageBox(QMessageBox.Icon.Question, tr("ui.unsaved_title"), tr("ui.unsaved_text"), parent=self)
        buttons = {
            box.addButton(QMessageBox.StandardButton.Save): "save",
            box.addButton(QMessageBox.StandardButton.Discard): "discard",
            box.addButton(QMessageBox.StandardButton.Cancel): "cancel",
        }
        box.exec()
        return buttons.get(box.clickedButton(), "cancel")

    def _ask_open_path(self, file_filter: str) -> str | None:
        path, _ = QFileDialog.getOpenFileName(self, "", "", file_filter)
        return path or None

    def _ask_save_path(self, file_filter: str, default: str) -> str | None:
        path, _ = QFileDialog.getSaveFileName(self, "", default, file_filter)
        return path or None

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
        if path := self._ask_open_path(tr("ui.filter_tables")):
            self.add_run(path)

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


def run(project: Path | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("qpcrkit")
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

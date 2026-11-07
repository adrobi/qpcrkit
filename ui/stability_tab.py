"""The stability page: which genes to take as references, and how many."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from i18n import tr
from qpcr_core.editing import set_references, set_stability_candidate
from qpcr_core.figures import genorm_figure, normfinder_figure
from qpcr_core.models import Project
from qpcr_core.pipeline import Results
from qpcr_core.stability import stability_candidates
from ui.canvas import FigureCanvas
from ui.editor import ProjectEditor
from ui.result_tabs import _table
from ui.theme import mpl_style


class StabilityTab(QWidget):
    def __init__(self, editor: ProjectEditor) -> None:
        super().__init__()
        self.editor = editor
        self.candidate_checks: dict[str, QCheckBox] = {}
        self._recommended: tuple[str, ...] = ()
        self._candidates: list[str] = []

        title = QLabel(tr("stab.candidates"))
        title.setObjectName("dim")
        self._check_box = QWidget()
        self._check_layout = QVBoxLayout(self._check_box)
        self._check_layout.setContentsMargins(0, 0, 0, 0)
        self._check_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._check_box)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(title)
        left_layout.addWidget(scroll, 1)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setObjectName("projectName")
        self.apply_button = QPushButton(tr("stab.apply"))
        self.apply_button.setObjectName("primaryBtn")
        self.apply_button.clicked.connect(self._apply_advice)
        self.need_more = QLabel()
        self.need_more.setWordWrap(True)
        self.notes = QLabel()
        self.notes.setWordWrap(True)
        self.notes.setObjectName("dim")
        self.genorm_canvas = FigureCanvas()
        self.normfinder_canvas = FigureCanvas()
        self.normfinder_table = QTableWidget()
        self.best_pair = QLabel()

        head = QHBoxLayout()
        head.addWidget(self.summary, 1)
        head.addWidget(self.apply_button)
        normfinder = QWidget()
        nf_layout = QVBoxLayout(normfinder)
        nf_layout.setContentsMargins(0, 0, 0, 0)
        nf_layout.addWidget(self.normfinder_canvas, 2)
        nf_layout.addWidget(self.normfinder_table, 1)
        nf_layout.addWidget(self.best_pair)
        figures = QSplitter(Qt.Orientation.Horizontal)
        figures.addWidget(self.genorm_canvas)
        figures.addWidget(normfinder)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addLayout(head)
        right_layout.addWidget(self.need_more)
        right_layout.addWidget(self.notes)
        right_layout.addWidget(figures, 1)
        self._figures = figures

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([220, 900])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(splitter)

    # --- results ---

    def set_results(self, project: Project, results: Results, dark: bool) -> None:
        self._candidates = stability_candidates(project)
        self._fill_checks(project, results)
        s = results.stability
        computed = s is not None and bool(s.genorm_m)
        self._recommended = s.recommended if computed else ()
        self.need_more.setVisible(not computed)
        self.need_more.setText(
            " ".join(tr(f"stab.note.{n}") for n in (s.notes if s else ("few_candidates",)) if n.startswith("few")) if not computed else ""
        )
        self.genorm_canvas.setVisible(computed)
        self.normfinder_canvas.setVisible(computed and bool(s.normfinder_rho))
        self.normfinder_table.setVisible(computed and bool(s.normfinder_rho))
        other_notes = [tr(f"stab.note.{n}") for n in (s.notes if s else ()) if not n.startswith("few_candidates") and n != "few_samples"]
        self.notes.setText("\n".join(other_notes))
        self.notes.setVisible(bool(other_notes))
        style = mpl_style(dark)
        if computed:
            self.summary.setText(self._advice_text(s))
            self.genorm_canvas.set_figure(genorm_figure(s, style=style))
            if s.normfinder_rho:
                self.normfinder_canvas.set_figure(normfinder_figure(s, style=style))
                ranked = sorted(s.normfinder_rho, key=s.normfinder_rho.get)
                _table(self.normfinder_table, [tr("ui.target"), "ρ", tr("stab.rank")],
                       [[g, s.normfinder_rho[g], i + 1] for i, g in enumerate(ranked)])
            else:
                self.normfinder_canvas.set_figure(None)
                _table(self.normfinder_table, [tr("ui.target"), "ρ", tr("stab.rank")], [])
            self.best_pair.setText(tr("stab.best_pair", a=s.best_pair[0], b=s.best_pair[1], rho=s.best_pair_rho) if s.best_pair else "")
        else:
            self.summary.setText(tr("stab.title"))
            self.genorm_canvas.set_figure(None)
            self.normfinder_canvas.set_figure(None)
            _table(self.normfinder_table, [tr("ui.target"), "ρ", tr("stab.rank")], [])
            self.best_pair.setText("")
        self._update_button(project)

    def _fill_checks(self, project: Project, results: Results) -> None:
        while self._check_layout.count() > 1:
            widget = self._check_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self.candidate_checks = {}
        for name in sorted(project.targets):
            count = sum(1 for (_s, t), cq in results.mean_cq.items() if t == name and cq is not None)
            check = QCheckBox(tr("stab.candidate", name=name, n=count))
            with QSignalBlocker(check):
                check.setChecked(name in self._candidates)
            check.toggled.connect(lambda on, n=name: self.editor.apply(set_stability_candidate, n, on))
            self._check_layout.insertWidget(self._check_layout.count() - 1, check)
            self.candidate_checks[name] = check

    def _advice_text(self, s) -> str:
        genes = ", ".join(s.recommended)
        if "v_never_below" in s.notes:
            return tr("stab.advice_all", n=len(s.recommended), genes=genes)
        v = s.pairwise_v.get(len(s.recommended))
        if v is None:
            return tr("stab.advice_two", genes=genes)
        return tr("stab.advice", n=len(s.recommended), genes=genes, v=v)

    def _update_button(self, project: Project) -> None:
        references = {n for n in self._candidates if project.targets.get(n) and project.targets[n].kind == "reference"}
        self.apply_button.setEnabled(len(self._recommended) >= 2 and references != set(self._recommended))

    def _apply_advice(self) -> None:
        self.editor.apply(set_references, list(self._recommended), among=list(self._candidates))

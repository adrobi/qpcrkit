"""The curve graph beside the plate: selection is linked, and redraws only its top layer."""

from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QToolTip, QVBoxLayout, QWidget

from i18n import tr
from qpcr_core.curves import derivative_curve, run_uses_calculated, subtracted_curve
from qpcr_core.models import Project, Reaction, Well
from qpcr_core.pipeline import Results
from ui.plate_view import target_color_map
from ui.theme import icon, theme

_CLICK_PX = 5.0
_HOVER_MS = 30
_DIM_ALPHA = 0.25


class CurveView(QWidget):
    wells_clicked = Signal(list, bool)  # coords, add to the selection (Ctrl)
    threshold_changed = Signal(str, float)
    threshold_reset = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project: Project | None = None
        self.results: Results | None = None
        self.run_id: str | None = None
        self.dark = False
        self._selected: list[str] = []
        self._coords: list[str] = []  # one per drawn curve
        self._curves: list[np.ndarray] = []  # N x 2, data coordinates
        self._layers: dict[str, LineCollection] = {}
        self._background = None
        self._dimmed = False
        self._segments_px: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None
        self.threshold_line: Line2D | None = None
        self._threshold_target: str | None = None
        self._drag_from: float | None = None
        self._hover_pos: tuple[float, float] | None = None

        self.mode_combo = QComboBox()
        self.mode_combo.addItem(tr("ui.curves.amp"), "amp")
        self.mode_combo.addItem(tr("ui.curves.log"), "log")
        self.mode_combo.addItem(tr("ui.curves.melt"), "melt")
        self.target_combo = QComboBox()
        self.target_combo.addItem(tr("ui.curves.all"), "")
        self.auto_button = QPushButton(tr("ui.curves.auto"))
        self.auto_button.setToolTip(tr("ui.curves.auto_tip"))
        self.auto_button.hide()
        self.auto_button.clicked.connect(lambda: self.threshold_reset.emit(self._threshold_target or ""))
        self.placeholder = QLabel(tr("ui.curves.none"))
        self.placeholder.setObjectName("dim")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.figure = Figure()
        self.ax = self.figure.add_subplot()
        self.canvas = FigureCanvasQTAgg(self.figure)
        self._top = LineCollection([], linewidths=1.8, animated=True)  # drawn over a saved background
        self.ax.add_collection(self._top)
        # A veil over the saved picture dims the curves without drawing them again: one full draw
        # of 768 curves takes 300 ms, and a selection has 100.
        self._veil = Rectangle((0, 0), 1, 1, transform=self.ax.transAxes, alpha=1 - _DIM_ALPHA, animated=True, zorder=2)
        self.ax.add_patch(self._veil)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addWidget(self.mode_combo)
        bar.addWidget(self.target_combo)
        bar.addWidget(self.auto_button)
        bar.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(bar)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.placeholder, 1)

        self._hover_timer = QTimer(self, singleShot=True, interval=_HOVER_MS)
        self._hover_timer.timeout.connect(self._show_hover)
        self.canvas.mpl_connect("draw_event", self._on_draw)
        self.canvas.mpl_connect("resize_event", self._fit_margins)
        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_release_event", self._on_release)
        self.mode_combo.currentIndexChanged.connect(self._rebuild)
        self.target_combo.currentIndexChanged.connect(self._rebuild)
        self._apply_theme()
        self._fit_margins()
        self._rebuild()

    def _fit_margins(self, *_args) -> None:
        """Margins in pixels: as fractions they cut the axis labels on a narrow graph."""
        width, height = self.figure.bbox.width, self.figure.bbox.height
        if width > 120 and height > 120:
            self.figure.subplots_adjust(left=66 / width, right=1 - 12 / width, bottom=44 / height, top=1 - 10 / height)

    # --- data --------------------------------------------------------------------------------

    def set_data(self, project: Project | None, results: Results | None, run_id: str | None) -> None:
        self.project, self.results, self.run_id = project, results, run_id
        run = project.run(run_id) if project and run_id else None
        names = sorted({r.target for w in run.wells.values() for r in w.reactions}) if run else []
        current = self.target_combo.currentData()
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        self.target_combo.addItem(tr("ui.curves.all"), "")
        for name in names:
            self.target_combo.addItem(name, name)
        index = self.target_combo.findData(current)
        self.target_combo.setCurrentIndex(max(index, 0))
        self.target_combo.blockSignals(False)
        self._rebuild()

    def _mode(self) -> str:
        return self.mode_combo.currentData() or "amp"

    def _reactions(self):
        if not (self.project and self.run_id):
            return
        chosen = self.target_combo.currentData()
        for well in self.project.run(self.run_id).wells.values():
            for rxn in well.reactions:
                if not rxn.excluded and (not chosen or rxn.target == chosen):
                    yield well, rxn

    def _rebuild(self, *_args) -> None:
        pick = derivative_curve if self._mode() == "melt" else subtracted_curve
        for layer in self._layers.values():
            layer.remove()
        self._layers = {}
        self._coords, self._curves = [], []
        by_target: dict[str, list[np.ndarray]] = {}
        for well, rxn in self._reactions() or ():
            curve = pick(rxn)
            if curve is None:
                continue
            xy = np.column_stack((curve.x, curve.y))
            self._coords.append(well.coord)
            self._curves.append(xy)
            by_target.setdefault(rxn.target, []).append(xy)

        colors = target_color_map(self.project.targets) if self.project else {}
        for target, lines in by_target.items():
            layer = LineCollection(self._for_axis(lines), colors=colors.get(target, "#2563eb"), linewidths=0.8)
            self.ax.add_collection(layer)
            self._layers[target] = layer

        has_lines = bool(self._curves)
        self.canvas.setVisible(has_lines)
        self.placeholder.setVisible(not has_lines)
        self._set_axes()
        self._background = None
        self._segments_px = None
        self._update_top()
        self._dimmed = bool(self._top.get_segments())
        self._update_threshold()
        self.canvas.draw_idle()

    def threshold_value(self) -> float | None:
        return float(self.threshold_line.get_ydata()[0]) if self.threshold_line is not None else None

    def _update_threshold(self) -> None:
        """A line only for one target on the graph: on several it would not say whose it is."""
        if self.threshold_line is not None:
            self.threshold_line.remove()
            self.threshold_line = None
        self._drag_from = None
        self._threshold_target = None
        self.auto_button.hide()
        if self._mode() == "melt" or len(self._layers) != 1:
            return
        target = next(iter(self._layers))
        run = self.project.run(self.run_id)
        value = run.thresholds.get(target)
        if value is None and self.results is not None:
            value = next((r.threshold for k, r in self.results.curves.items() if k[0] == run.id and k[2] == target and r.threshold), None)
        self._threshold_target = target
        self.auto_button.setVisible(target in run.thresholds)
        if value:
            color = theme("dark" if self.dark else "light")["text"]
            # Drawn with the top layer, over the veil: dimming must not hide what can be dragged.
            self.threshold_line = self.ax.axhline(value, color=color, linestyle="--", linewidth=1.2, animated=True)

    def _near_threshold(self, event) -> bool:
        if self.threshold_line is None or event.inaxes is not self.ax:
            return False
        level = self.ax.transData.transform((event.xdata, self.threshold_value()))[1]
        return abs(level - event.y) <= _CLICK_PX

    def _move_threshold(self, value: float) -> None:
        self.threshold_line.set_ydata([value, value])
        self._repaint()

    def _repaint(self) -> None:
        if self._background is None:
            self.canvas.draw()
            return
        self.canvas.restore_region(self._background)
        self._paint_top()

    def _on_release(self, event) -> None:
        if self._drag_from is None:
            return
        start, self._drag_from = self._drag_from, None
        inside = event.inaxes is self.ax and event.ydata is not None and event.ydata > 0
        self._move_threshold(event.ydata if inside else start)
        if inside:
            self.threshold_changed.emit(self._threshold_target, float(event.ydata))

    def _for_axis(self, lines: list[np.ndarray]) -> list[np.ndarray]:
        if self._mode() != "log":
            return lines
        return [np.column_stack((xy[:, 0], np.where(xy[:, 1] > 0, xy[:, 1], np.nan))) for xy in lines]

    def _set_axes(self) -> None:
        mode = self._mode()
        self.ax.set_yscale("log" if mode == "log" else "linear")
        self.ax.set_xlabel(tr("ui.curves.temperature") if mode == "melt" else tr("ui.curves.cycle"), fontsize=9)
        self.ax.set_ylabel(tr("ui.curves.dfdt") if mode == "melt" else tr("ui.curves.signal"), fontsize=9)
        if not self._curves:
            return
        points = np.concatenate(self._curves)
        self.ax.set_xlim(points[:, 0].min(), points[:, 0].max())
        top, bottom = float(points[:, 1].max()), float(points[:, 1].min())
        if mode == "log":
            positive = points[:, 1][points[:, 1] > 0]
            top = float(positive.max()) if positive.size else 1.0
            low = float(positive.min()) if positive.size else 0.1
            self.ax.set_ylim(max(low, top * 1e-4), top * 1.5)
        else:
            margin = (top - bottom) * 0.05 or 1.0
            self.ax.set_ylim(bottom - margin, top + margin)

    # --- selection ---------------------------------------------------------------------------

    def set_selection(self, coords: list[str]) -> None:
        self._selected = list(coords)
        self._update_top()
        if not self._curves:
            return
        self._dimmed = bool(self._top.get_segments())
        self._repaint()

    def _update_top(self) -> None:
        wanted = set(self._selected)
        lines = [xy for coord, xy in zip(self._coords, self._curves) if coord in wanted]
        self._top.set_segments(self._for_axis(lines))

    def _on_draw(self, _event) -> None:
        """After every full draw, which also happens on a resize: the saved pictures are out of date."""
        self._background = self.canvas.copy_from_bbox(self.figure.bbox)
        self._segments_px = None
        self._paint_top()

    def _paint_top(self) -> None:
        if self._dimmed:
            self.ax.draw_artist(self._veil)
        self.ax.draw_artist(self._top)
        if self.threshold_line is not None:
            self.ax.draw_artist(self.threshold_line)
        self.canvas.blit(self.figure.bbox)

    def line_count(self) -> int:
        return len(self._curves)

    def selected_line_count(self) -> int:
        return len(self._top.get_segments())

    def layer_alpha(self) -> float:
        return _DIM_ALPHA if self._dimmed else 1.0

    # --- mouse -------------------------------------------------------------------------------

    def _pixel_segments(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """All segments of all curves in display coordinates, at once: hovering cannot afford a loop."""
        if self._segments_px is None:
            starts, ends, owners = [], [], []
            for index, xy in enumerate(self._for_axis(self._curves)):
                px = self.ax.transData.transform(xy)
                starts.append(px[:-1])
                ends.append(px[1:])
                owners.append(np.full(len(xy) - 1, index))
            self._segments_px = (np.concatenate(starts), np.concatenate(ends), np.concatenate(owners))
        return self._segments_px

    def coord_at(self, x_px: float, y_px: float) -> str | None:
        """The well of the nearest curve within a few pixels."""
        if not self._curves:
            return None
        a, b, owners = self._pixel_segments()
        point = np.array((x_px, y_px))
        along = b - a
        with np.errstate(invalid="ignore", divide="ignore"):
            t = np.clip(((point - a) * along).sum(axis=1) / (along * along).sum(axis=1), 0.0, 1.0)
        t = np.where(np.isnan(t), 0.0, t)
        distance = np.hypot(*(a + along * t[:, None] - point).T)
        if np.isnan(distance).all():
            return None
        nearest = int(np.nanargmin(distance))
        return self._coords[owners[nearest]] if distance[nearest] <= _CLICK_PX else None

    def _on_press(self, event) -> None:
        if event.button != 1 or event.inaxes is not self.ax:
            return
        if self._near_threshold(event):
            self._drag_from = self.threshold_value()
            return
        coord = self.coord_at(event.x, event.y)
        if coord is not None:
            self.wells_clicked.emit([coord], "ctrl" in (event.modifiers or ()))

    def _on_motion(self, event) -> None:
        if self._drag_from is not None:
            if event.inaxes is self.ax and event.ydata is not None and event.ydata > 0:
                self._move_threshold(float(event.ydata))
            return
        near = self._near_threshold(event)
        self.canvas.setCursor(Qt.CursorShape.SizeVerCursor if near else Qt.CursorShape.ArrowCursor)
        self._hover_pos = (event.x, event.y) if event.inaxes is self.ax else None
        if not self._hover_timer.isActive():
            self._hover_timer.start()

    def _show_hover(self) -> None:
        coord = self.coord_at(*self._hover_pos) if self._hover_pos else None
        if coord is None:
            QToolTip.hideText()
        else:
            QToolTip.showText(QCursor.pos(), self.hover_text(coord), self.canvas)

    def hover_text(self, coord: str) -> str:
        run = self.project.run(self.run_id)
        well = run.wells[coord]
        return "\n".join(self._reaction_text(run, well, r) for _w, r in self._reactions() or () if _w is well)

    def _reaction_text(self, run, well: Well, rxn: Reaction) -> str:
        result = self.results.curves.get((run.id, well.coord, rxn.target, rxn.fluor)) if self.results else None
        calculated = run_uses_calculated(run, self.project.settings)
        cq = (result.cq_calc if result else None) if calculated else rxn.cq
        shown = f"{cq:.2f}" if cq is not None else "—"
        return f"{well.coord} · {well.sample or '—'} · {rxn.target} · Cq {shown}"

    # --- theme -------------------------------------------------------------------------------

    def set_theme(self, dark: bool) -> None:
        self.dark = bool(dark)
        self._apply_theme()
        self._background = None
        self.canvas.draw_idle()

    def _apply_theme(self) -> None:
        t = theme("dark" if self.dark else "light")
        self.figure.set_facecolor(t["bg"])
        self.ax.set_facecolor(t["bg"])
        for spine in self.ax.spines.values():
            spine.set_color(t["border"])
        self.ax.spines["top"].set_visible(False)
        self.ax.spines["right"].set_visible(False)
        self.ax.tick_params(colors=t["dim"], labelsize=8)
        self.ax.xaxis.label.set_color(t["dim"])
        self.ax.yaxis.label.set_color(t["dim"])
        self.ax.grid(True, color=t["grid"], linewidth=0.5)
        self.ax.set_axisbelow(True)
        self._top.set_color(t["accent"])
        self._veil.set_facecolor(t["bg"])
        self._veil.set_edgecolor("none")
        if self.threshold_line is not None:
            self.threshold_line.set_color(t["text"])
        self.auto_button.setIcon(icon("rotate-ccw", t["dim"]))

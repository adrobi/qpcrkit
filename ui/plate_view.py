"""Interactive qPCR run plate view for qpcrkit."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from qpcr_core.models import PLATE_FORMATS, Project, Run, Well, format_coord, parse_coord
from ui.theme import theme

TARGET_PALETTE = [
    "#2563eb",
    "#059669",
    "#d97706",
    "#dc2626",
    "#7c3aed",
    "#db2777",
    "#0891b2",
    "#65a30d",
    "#ea580c",
    "#4f46e5",
]

ROLE_COLORS = {
    "unknown": "#2563eb",
    "ntc": "#9ca3af",
    "std": "#10b981",
    "irc": "#8b5cf6",
    "pos": "#f59e0b",
}


class PlateView(QWidget):
    """Custom painted plate map for qPCR results."""

    selection_changed = Signal()
    exclude_toggled = Signal(str)

    HEADER = 24
    PADDING = 8

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.run: Run | None = None
        self.project: Project | None = None
        self.dark: bool = False
        self.color_mode: str = "target"
        self.compact: bool = False  # a 384 plate: no labels in the wells, small headers
        self._selection: set[tuple[int, int]] = set()
        self._target_colors: dict[str, str] = {}
        self._drag_start: tuple[int, int] | None = None
        self._drag_additive: bool = False
        self._drag_base: set[tuple[int, int]] = set()

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(360, 260)

    def set_run(self, run: Run | None, project: Project | None) -> None:
        """Bind the view to a run and project."""
        self.run = run
        self.project = project
        self.compact = bool(run and run.plate_format == 384)
        self._build_target_colors()
        self._selection.clear()
        self.update()
        self.selection_changed.emit()

    def set_theme(self, dark: bool) -> None:
        """Switch between light and dark palettes."""
        self.dark = bool(dark)
        self.update()

    def set_color_mode(self, mode: str) -> None:
        """Set well colouring mode: target or role."""
        self.color_mode = mode if mode in ("target", "role") else "target"
        self.update()

    def selected_coords(self) -> list[str]:
        """Return selected coordinates sorted by row then column."""
        return [self._coord_for_cell(r, c) for r, c in sorted(self._selection)]

    def select_coords(self, coords: list[str]) -> None:
        """Replace the selection with the given coordinates."""
        new_selection: set[tuple[int, int]] = set()
        for coord in coords:
            cell = self._cell_for_coord(coord)
            if cell is not None:
                new_selection.add(cell)
        self._selection = new_selection
        self.update()
        self.selection_changed.emit()

    def header_rect(self, kind: str, index: int) -> QRect:
        """Return a row or column header cell rectangle in widget coordinates."""
        x0, y0, cell, rows, cols = self._layout()
        if kind == "row" and 0 <= index < rows:
            return QRect(
                int(round(x0 - self.HEADER)),
                int(round(y0 + index * cell)),
                int(round(self.HEADER)),
                int(round(cell)),
            )
        if kind == "col" and 0 <= index < cols:
            return QRect(
                int(round(x0 + index * cell)),
                int(round(y0 - self.HEADER)),
                int(round(cell)),
                int(round(self.HEADER)),
            )
        return QRect()

    # --- Geometry ---

    def _layout(self) -> tuple[float, float, float, int, int]:
        """Return (x0, y0, cell, rows, cols) for the current widget size."""
        rows, cols = self._rows_cols()
        avail_w = max(1.0, self.width() - self.HEADER - 2 * self.PADDING)
        avail_h = max(1.0, self.height() - self.HEADER - 2 * self.PADDING)
        cell = max(1.0, min(avail_w / cols, avail_h / rows))
        grid_w = cell * cols
        grid_h = cell * rows
        x0 = self.PADDING + self.HEADER + (avail_w - grid_w) / 2.0
        y0 = self.PADDING + self.HEADER + (avail_h - grid_h) / 2.0
        return x0, y0, cell, rows, cols

    def _rows_cols(self) -> tuple[int, int]:
        if self.run is None:
            return 8, 12
        shape = PLATE_FORMATS.get(self.run.plate_format)
        if shape is not None:
            return shape
        n = self._rotor_n()
        return max(1, math.ceil(n / 12)), 12

    def _is_rotor(self) -> bool:
        return self.run is not None and PLATE_FORMATS.get(self.run.plate_format) is None

    def _rotor_n(self) -> int:
        if self.run is None:
            return 0
        n = self.run.plate_format if self.run.plate_format > 0 else 0
        if n <= 0:
            n = len(self.run.wells)
        for key in self.run.wells:
            if key.isdigit():
                n = max(n, int(key))
        return n

    def _valid_cell(self, row: int, col: int) -> bool:
        rows, cols = self._rows_cols()
        if not (0 <= row < rows and 0 <= col < cols):
            return False
        if self._is_rotor():
            return row * 12 + col + 1 <= self._rotor_n()
        return True

    def _coord_for_cell(self, row: int, col: int) -> str:
        if self._is_rotor():
            return str(row * 12 + col + 1)
        return format_coord(row, col)

    def _cell_for_coord(self, coord: str) -> tuple[int, int] | None:
        coord = coord.strip()
        if self._is_rotor():
            try:
                index = int(coord)
            except ValueError:
                return None
            if not 1 <= index <= self._rotor_n():
                return None
            row, col = divmod(index - 1, 12)
            return (row, col) if self._valid_cell(row, col) else None
        try:
            row, col = parse_coord(coord)
        except ValueError:
            return None
        return (row, col) if self._valid_cell(row, col) else None

    def _cell_at(self, pos: QPointF) -> tuple[int, int] | None:
        x0, y0, cell, rows, cols = self._layout()
        x, y = pos.x(), pos.y()
        if x < x0 or y < y0 or x >= x0 + cols * cell or y >= y0 + rows * cell:
            return None
        col = int((x - x0) / cell)
        row = int((y - y0) / cell)
        return (row, col) if self._valid_cell(row, col) else None

    def _header_at(self, pos: QPointF) -> tuple[str, int] | None:
        x0, y0, cell, rows, cols = self._layout()
        x, y = pos.x(), pos.y()
        h = self.HEADER
        if x0 - h <= x < x0 and y0 - h <= y < y0:
            return "corner", -1
        if y0 - h <= y < y0 and x0 <= x < x0 + cols * cell:
            return "col", int((x - x0) / cell)
        if x0 - h <= x < x0 and y0 <= y < y0 + rows * cell:
            return "row", int((y - y0) / cell)
        return None

    # --- Selection ---

    def _change_selection(self, cells: set[tuple[int, int]]) -> None:
        if cells != self._selection:
            self._selection = cells
            self.update()
            self.selection_changed.emit()

    def _all_cells(self) -> set[tuple[int, int]]:
        rows, cols = self._rows_cols()
        return {
            (row, col)
            for row in range(rows)
            for col in range(cols)
            if self._valid_cell(row, col)
        }

    def _build_target_colors(self) -> None:
        names: set[str] = set()
        if self.project is not None:
            names.update(self.project.targets)
        if self.run is not None:
            for well in self.run.wells.values():
                for reaction in well.reactions:
                    if reaction.target:
                        names.add(reaction.target)
        self._target_colors = {
            name: TARGET_PALETTE[i % len(TARGET_PALETTE)]
            for i, name in enumerate(sorted(names))
        }

    # --- Painting ---

    def _well_style(
        self, well: Well | None, pal: dict
    ) -> tuple[QColor, QColor, str, bool, bool]:
        if well is None:
            return (
                QColor(pal["well_empty"]),
                QColor(pal["well_border"]),
                "—",
                False,
                False,
            )

        reactions = well.reactions
        all_excluded = bool(reactions) and all(r.excluded for r in reactions)
        partly_excluded = bool(reactions) and any(r.excluded for r in reactions) and not all_excluded

        if self.color_mode == "role":
            role = reactions[0].role if reactions else "unknown"
            base = QColor(pal["accent"] if role == "unknown" else ROLE_COLORS.get(role, pal["accent"]))
        else:
            target = reactions[0].target if reactions else ""
            base = QColor(self._target_colors.get(target, pal["accent"]))

        fill = QColor(base)
        fill.setAlpha(105 if self.dark else 75)
        if all_excluded:
            fill.setAlpha(40 if self.dark else 28)

        border = QColor(pal["qc_err"]) if all_excluded else base
        cq = None
        for reaction in reactions:
            if not reaction.excluded:
                cq = reaction.cq
                break
        label = f"{cq:.1f}" if cq is not None else "—"
        return fill, border, label, all_excluded, partly_excluded

    def paintEvent(self, _event) -> None:
        pal = theme("dark" if self.dark else "light")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(pal["bg"]))

        x0, y0, cell, rows, cols = self._layout()
        h = self.HEADER

        header_font = QFont(self.font())
        header_font.setBold(True)
        header_font.setPointSize(7 if self.compact else max(6, min(10, int(cell * 0.24))))
        painter.setFont(header_font)

        corner = QRectF(x0 - h, y0 - h, h, h).adjusted(1, 1, -1, -1)
        painter.setPen(QPen(QColor(pal["grid"]), 1))
        painter.setBrush(QColor(pal["header_bg"]))
        painter.drawRoundedRect(corner, 4, 4)
        painter.setPen(QColor(pal["dim"]))
        painter.drawText(corner, Qt.AlignmentFlag.AlignCenter, "◢")

        for col in range(cols):
            rect = QRectF(x0 + col * cell + 1, y0 - h + 1, cell - 2, h - 2)
            painter.setPen(QPen(QColor(pal["grid"]), 1))
            painter.setBrush(QColor(pal["header_bg"]))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(QColor(pal["text"]))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(col + 1))

        for row in range(rows):
            rect = QRectF(x0 - h + 1, y0 + row * cell + 1, h - 2, cell - 2)
            painter.setPen(QPen(QColor(pal["grid"]), 1))
            painter.setBrush(QColor(pal["header_bg"]))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(QColor(pal["text"]))
            label = str(row + 1) if self._is_rotor() else chr(ord("A") + row)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

        for row in range(rows):
            for col in range(cols):
                if not self._valid_cell(row, col):
                    continue
                coord = self._coord_for_cell(row, col)
                well = self.run.wells.get(coord) if self.run is not None else None
                margin = max(1.0, min(2.5, cell * 0.04))
                rect = QRectF(
                    x0 + col * cell + margin,
                    y0 + row * cell + margin,
                    cell - 2 * margin,
                    cell - 2 * margin,
                )

                fill, border, label, excluded, partly_excluded = self._well_style(well, pal)
                painter.setBrush(fill)
                if (row, col) in self._selection:
                    painter.setPen(QPen(QColor(pal["selection"]), 2.0))
                else:
                    painter.setPen(QPen(border, 1.2))
                radius = 3.0 if rows >= 16 or cols >= 24 else 5.0
                painter.drawRoundedRect(rect, radius, radius)

                if excluded:
                    painter.setPen(QPen(QColor(pal["qc_err"]), max(1.0, cell * 0.05)))
                    painter.drawLine(rect.topLeft(), rect.bottomRight())

                if partly_excluded:
                    mark = max(3.0, min(6.0, cell * 0.14))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(pal["qc_warn"]))
                    painter.drawEllipse(
                        QRectF(rect.right() - mark - 2, rect.top() + 2, mark, mark)
                    )

                if cell >= 12 and not self.compact:
                    font = QFont(self.font())
                    font.setPointSize(max(6, min(11, int(cell * 0.24))))
                    painter.setFont(font)
                    painter.setPen(QColor(pal["text"]))
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

    # --- Mouse interaction ---

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        mods = event.modifiers()
        additive = bool(mods & Qt.KeyboardModifier.ControlModifier)

        if mods & Qt.KeyboardModifier.AltModifier:
            cell = self._cell_at(pos)
            if cell is not None:
                self.exclude_toggled.emit(self._coord_for_cell(*cell))
                return

        header = self._header_at(pos)
        if header is not None:
            kind, index = header
            if kind == "corner":
                self._change_selection(self._all_cells())
            elif kind == "col":
                rows, _cols = self._rows_cols()
                cells = {
                    (row, index)
                    for row in range(rows)
                    if self._valid_cell(row, index)
                }
                self._change_selection(self._selection | cells if additive else cells)
            elif kind == "row":
                _rows, cols = self._rows_cols()
                cells = {
                    (index, col)
                    for col in range(cols)
                    if self._valid_cell(index, col)
                }
                self._change_selection(self._selection | cells if additive else cells)
            return

        cell = self._cell_at(pos)
        if cell is None:
            return
        self._drag_start = cell
        self._drag_additive = additive
        self._drag_base = set(self._selection) if additive else set()
        cells = (self._drag_base | {cell}) if additive else {cell}
        self._change_selection(cells)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self._drag_start is None:
            return
        cell = self._cell_at(event.position())
        if cell is None:
            return
        r0, c0 = self._drag_start
        r1, c1 = cell
        cells = {
            (row, col)
            for row in range(min(r0, r1), max(r0, r1) + 1)
            for col in range(min(c0, c1), max(c0, c1) + 1)
            if self._valid_cell(row, col)
        }
        if self._drag_additive:
            cells |= self._drag_base
        self._change_selection(cells)

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:
        self._drag_start = None

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        cell = self._cell_at(event.position())
        if cell is not None:
            self.exclude_toggled.emit(self._coord_for_cell(*cell))

"""Shared pieces for instrument importers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..models import Project, Reaction, Run, Sample, Well, format_coord, parse_coord
from .textio import UnsupportedFileError, detect_number_style, parse_number  # noqa: F401


@dataclass
class ImportReport:
    run: Run
    samples: dict[str, Sample] = field(default_factory=dict)
    total_rows: int = 0
    imported: int = 0
    skipped: list[tuple[int, str]] = field(default_factory=list)  # (1-based row number, reason)
    notes: list[str] = field(default_factory=list)  # things the user should know about this import
    suggested_refs: list[str] = field(default_factory=list)  # reference targets named by the file
    suggested_calibrator: str = ""  # reference sample named by the file


class UnknownFormatError(Exception):
    pass


def map_role(text: str) -> str:
    t = text.strip().lower()
    if t.startswith(("std", "standard")):
        return "std"
    if t.startswith(("nrt", "no rt", "no reverse", "-rt")):
        return "nrt"
    if t.startswith(("ntc", "neg", "negative")):
        return "ntc"
    if t.startswith("pos"):
        return "pos"
    if t == "irc":
        return "irc"
    return "unknown"


def find_header(rows: list[list[str]], *required: str) -> int | None:
    """Index of the first row containing all ``required`` cells (case-insensitive)."""
    need = {r.lower() for r in required}
    for i, row in enumerate(rows):
        if need <= {c.lower() for c in row}:
            return i
    return None


def column_index(header: list[str]) -> dict[str, int]:
    return {c.strip().lower(): i for i, c in enumerate(header) if c.strip()}


def normalize_coord(coord: str) -> str:
    """'A01' -> 'A1'; numeric rotor positions are kept as they are."""
    coord = coord.strip()
    if coord.isdigit():
        return str(int(coord))
    return format_coord(*parse_coord(coord))


class ReportBuilder:
    def __init__(self, run: Run):
        self.report = ImportReport(run=run)

    def row(self) -> None:
        self.report.total_rows += 1

    def skip(self, row_number: int, reason: str) -> None:
        self.report.skipped.append((row_number, reason))

    def note(self, text: str) -> None:
        if text not in self.report.notes:
            self.report.notes.append(text)

    def number_reader(self, cells: list[str], name: str, delimiter: str | None) -> Callable[[str], float | None]:
        """A parser for one column: what a comma means is decided from the whole column."""
        style, ambiguous = detect_number_style(cells, delimiter)
        if ambiguous:
            sample = next(c for c in cells if "," in c)
            self.note(f"{name}: {sample!r} was read as {parse_number(sample, style):g} (comma as thousands)")
        return lambda s: parse_number(s, style)

    def add(
        self,
        coord: str,
        sample: str,
        reaction: Reaction,
        group: str = "",
    ) -> None:
        well = self.report.run.wells.setdefault(coord, Well(coord))
        if sample:
            well.sample = sample
            s = self.report.samples.setdefault(sample, Sample(sample))
            if group and not s.group:
                s.group = group
        well.reactions.append(reaction)
        self.report.imported += 1


def add_report(project: Project, report: ImportReport) -> None:
    """Append an imported run to the project, merging sample groups and creating targets."""
    project.runs.append(report.run)
    for name, s in report.samples.items():
        existing = project.samples.setdefault(name, Sample(name))
        if s.group and not existing.group:
            existing.group = s.group
    project.ensure_targets_and_samples()

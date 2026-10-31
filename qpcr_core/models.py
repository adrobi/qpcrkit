"""Data model: project → runs (plates) → wells → reactions (well × target)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

ROLES = ("unknown", "ntc", "std", "irc", "pos")

# (rows, cols) for grid plates; None = Rotor-Gene rotor, positions "1".."N"
PLATE_FORMATS: dict[int, tuple[int, int] | None] = {
    96: (8, 12),
    384: (16, 24),
    36: None,
    72: None,
    100: None,
}

_COORD_RE = re.compile(r"^\s*([A-Pa-p])0*(\d{1,2})\s*$")


def parse_coord(coord: str) -> tuple[int, int]:
    """'B12' / 'b012' -> (1, 11), zero-based row and column."""
    m = _COORD_RE.match(coord)
    if not m:
        raise ValueError(f"Unrecognized well coordinate: {coord!r}")
    col = int(m.group(2))
    if not 1 <= col <= 24:
        raise ValueError(f"Unrecognized well coordinate: {coord!r}")
    return ord(m.group(1).upper()) - ord("A"), col - 1


def format_coord(row: int, col: int) -> str:
    return f"{chr(ord('A') + row)}{col + 1}"


def coord_from_index(index: int, plate_format: int) -> str:
    """1-based row-major well index -> coordinate; Rotor-Gene positions stay numeric."""
    shape = PLATE_FORMATS.get(plate_format)
    if shape is None:
        return str(index)
    rows, cols = shape
    if not 1 <= index <= rows * cols:
        raise ValueError(f"Well index {index} out of range for {plate_format}-well plate")
    return format_coord((index - 1) // cols, (index - 1) % cols)


@dataclass
class Curve:
    x: list[float]
    y: list[float]


@dataclass
class Reaction:
    target: str
    fluor: str = ""
    role: str = "unknown"
    cq: float | None = None
    quantity: float | None = None
    excluded: bool = False
    exclude_reason: str = ""
    amplification: Curve | None = None
    melt: Curve | None = None


@dataclass
class Well:
    coord: str
    sample: str | None = None
    reactions: list[Reaction] = field(default_factory=list)


@dataclass
class Run:
    id: str
    name: str
    source_file: str = ""
    instrument: str = "generic"
    plate_format: int = 96
    wells: dict[str, Well] = field(default_factory=dict)


@dataclass
class Target:
    name: str
    kind: str = "target"  # target | reference
    efficiency_mode: str = "stdcurve"  # stdcurve | manual | ideal
    efficiency_manual: float | None = None


@dataclass
class Sample:
    name: str
    group: str = ""
    bio_replicate: str = ""


@dataclass
class Settings:
    control_group: str = ""
    calibrator_sample: str = ""
    test: str = "dunnett"  # dunnett | tukey
    error_bar: str = "sd"  # sd | sem | ci95
    rep_sd_max: float = 0.3
    ntc_cq_min: float = 35.0
    late_cq: float = 35.0
    eff_min: float = 0.90
    eff_max: float = 1.10
    r2_min: float = 0.98
    pool_std_runs: bool = True


@dataclass
class Project:
    runs: list[Run] = field(default_factory=list)
    targets: dict[str, Target] = field(default_factory=dict)
    samples: dict[str, Sample] = field(default_factory=dict)
    settings: Settings = field(default_factory=Settings)

    def iter_reactions(self) -> Iterator[tuple[Run, Well, Reaction]]:
        for run in self.runs:
            for well in run.wells.values():
                for rxn in well.reactions:
                    yield run, well, rxn

    def run(self, run_id: str) -> Run:
        for run in self.runs:
            if run.id == run_id:
                return run
        raise KeyError(run_id)

    def ensure_targets_and_samples(self) -> None:
        for _run, well, rxn in self.iter_reactions():
            if rxn.target and rxn.target not in self.targets:
                self.targets[rxn.target] = Target(rxn.target)
            if well.sample and well.sample not in self.samples:
                self.samples[well.sample] = Sample(well.sample)

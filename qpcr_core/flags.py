"""QC / analysis flags. Text comes from i18n key ``qc.<code>`` formatted with ``params``."""

from __future__ import annotations

from dataclasses import dataclass, field

SEVERITIES = ("error", "warning", "info")


@dataclass
class Flag:
    severity: str
    code: str
    params: dict = field(default_factory=dict)
    run_id: str | None = None
    coords: tuple[str, ...] = ()
    target: str | None = None
    sample: str | None = None

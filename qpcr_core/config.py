"""Application configuration (~/.config/qpcrkit/config.json)."""

from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "qpcrkit" / "config.json"


@dataclass
class AppConfig:
    dark: bool = False
    language: str = "auto"
    recent: list[str] = field(default_factory=list)
    csv_presets: dict[str, dict] = field(default_factory=dict)

    def add_recent(self, path: str | os.PathLike, max_items: int = 10) -> None:
        p = str(path)
        self.recent = [p] + [r for r in self.recent if r != p]
        del self.recent[max_items:]


def load_config(path: Path = CONFIG_PATH) -> AppConfig:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return AppConfig()
    if not isinstance(data, dict):
        return AppConfig()
    names = {f.name for f in dataclasses.fields(AppConfig)}
    try:
        return AppConfig(**{k: v for k, v in data.items() if k in names})
    except TypeError:
        return AppConfig()


def save_config(cfg: AppConfig, path: Path = CONFIG_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dataclasses.asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")

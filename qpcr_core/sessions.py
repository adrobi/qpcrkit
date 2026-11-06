"""Project persistence (*.qpcrkit.json)."""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import qpcr_core

from .models import Curve, Project, Reaction, Run, Sample, Settings, Target, Well


class SessionError(Exception):
    pass


_CURVE_FIELDS = ("amplification", "melt", "melt_derivative")


def _compact_run(run: dict) -> None:
    """Curves of a run mostly share their x, and the digits past the 7th are the instrument's noise."""
    axes: dict[tuple[float, ...], int] = {}
    for well in run["wells"].values():
        for rxn in well["reactions"]:
            for name in _CURVE_FIELDS:
                curve = rxn[name]
                if curve is None:
                    continue
                x = tuple(round(v, 6) for v in curve["x"])
                rxn[name] = {"x_ref": axes.setdefault(x, len(axes)), "y": [float(f"{v:.7g}") for v in curve["y"]]}
    run["curve_axes"] = [list(x) for x in axes]


def project_to_dict(p: Project) -> dict:
    d = dataclasses.asdict(p)
    for run in d["runs"]:
        _compact_run(run)
    return d


def _known(cls: type, data: dict) -> dict[str, Any]:
    names = {f.name for f in dataclasses.fields(cls)}
    return {k: v for k, v in data.items() if k in names}


def _curve(d: dict | None, axes: list[tuple[float, ...]]) -> Curve | None:
    if d is None:
        return None
    return Curve(axes[d["x_ref"]], d["y"]) if "x_ref" in d else Curve(**_known(Curve, d))


def _reaction(d: dict, axes: list[tuple[float, ...]]) -> Reaction:
    kw = _known(Reaction, d)
    for name in _CURVE_FIELDS:
        kw[name] = _curve(kw.get(name), axes)
    return Reaction(**kw)


def _well(d: dict, axes: list[tuple[float, ...]]) -> Well:
    kw = _known(Well, d)
    kw["reactions"] = [_reaction(r, axes) for r in kw.get("reactions") or []]
    return Well(**kw)


def _run(d: dict) -> Run:
    kw = _known(Run, d)
    axes = [tuple(x) for x in d.get("curve_axes") or []]
    kw["wells"] = {k: _well(w, axes) for k, w in (kw.get("wells") or {}).items()}
    return Run(**kw)


def project_from_dict(d: dict) -> Project:
    return Project(
        runs=[_run(r) for r in d.get("runs") or []],
        targets={k: Target(**_known(Target, v)) for k, v in (d.get("targets") or {}).items()},
        samples={k: Sample(**_known(Sample, v)) for k, v in (d.get("samples") or {}).items()},
        settings=Settings(**_known(Settings, d.get("settings") or {})),
    )


def save_project(p: Project, path: str | os.PathLike) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        {"app": "qpcrkit", "version": qpcr_core.__version__, "project": project_to_dict(p)},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        if path.exists():
            shutil.copy2(path, str(path) + ".bak")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_project(path: str | os.PathLike) -> Project:
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SessionError(f"Cannot read project file {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("app") != "qpcrkit":
        raise SessionError(f"Not a qpcrkit project file: {path}")
    try:
        return project_from_dict(payload["project"])
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise SessionError(f"Invalid project data in {path}: {exc}") from exc

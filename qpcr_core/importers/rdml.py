"""RDML 1.0 and 1.1 (Real-time PCR Data Markup Language): ZIP with an XML document."""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from pathlib import Path

from ..models import PLATE_FORMATS, Curve, Reaction, Run, coord_from_index, format_coord, parse_coord
from .base import ImportReport, ReportBuilder, normalize_coord
from .textio import parse_cq, parse_number

_MAX_XML_BYTES = 200 * 1024 * 1024
_GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_ROLES = {"unkn": "unknown", "std": "std", "ntc": "ntc", "nac": "ntc", "ntp": "ntc", "nrt": "nrt", "pos": "pos"}


class RdmlError(ValueError):
    pass


def is_rdml(path: str | os.PathLike) -> bool:
    return Path(path).suffix.lower() == ".rdml"


def _read_xml(path: Path) -> bytes:
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            name = "rdml_data.xml" if "rdml_data.xml" in names else next(n for n in names if n.lower().endswith(".xml"))
            if z.getinfo(name).file_size > _MAX_XML_BYTES:
                raise RdmlError(f"RDML document is too large: {path}")
            return z.read(name)
    except StopIteration:
        raise RdmlError(f"No RDML document inside: {path}") from None
    except (zipfile.BadZipFile, OSError) as exc:
        raise RdmlError(f"Cannot read RDML file {path}: {exc}") from exc


def _parse_root(path: Path) -> ET.Element:
    raw = _read_xml(path)
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:  # RDML needs neither; refuse entity tricks
        raise RdmlError(f"Refusing an RDML document with a DOCTYPE: {path}")
    try:
        return ET.fromstring(raw)
    except ET.ParseError as exc:
        raise RdmlError(f"Damaged RDML file {path}: {exc}") from exc


def _target_name(target_id: str, dye: str) -> str:
    """LightCycler writes "FAM@bACT", or "FAM@<guid>" for an unnamed target."""
    if "@" not in target_id:
        return target_id
    left, right = target_id.split("@", 1)
    return left if _GUID.match(right) else right


def _plate_layout(ids: list[str], rows: float | None, cols: float | None) -> tuple[int, Callable[[str], str]]:
    """The plate format and how reaction ids map to wells."""
    if rows and cols:
        r, c = int(rows), int(cols)
        if r == 1 or c == 1:  # a rotor has positions, not rows
            size = r * c
            return (size if size in PLATE_FORMATS and PLATE_FORMATS[size] is None else 72), lambda i: str(int(i))
        plate = 384 if r * c > 96 else 96
        return plate, lambda i: format_coord((int(i) - 1) // c, (int(i) - 1) % c) if i.isdigit() else normalize_coord(i)

    def beyond_96(i: str) -> bool:
        if i.isdigit():
            return int(i) > 96
        try:
            row, col = parse_coord(i)
        except ValueError:
            return False
        return row > 7 or col > 11

    plate = 384 if len(ids) > 96 or any(beyond_96(i) for i in ids) else 96
    return plate, lambda i: coord_from_index(int(i), plate) if i.isdigit() else normalize_coord(i)


def _curve(points: list[ET.Element], x_tag: str, ns: str) -> Curve | None:
    xy = []
    for p in points:
        x, y = parse_number(p.findtext(ns + x_tag) or ""), parse_number(p.findtext(ns + "fluor") or "")
        if x is not None and y is not None:
            xy.append((x, y))
    if not xy:
        return None
    xy.sort()
    return Curve([a for a, _ in xy], [b for _, b in xy])


def parse_rdml(path: str | os.PathLike, first_run_index: int = 1) -> list[ImportReport]:
    path = Path(path)
    root = _parse_root(path)
    ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""

    samples: dict[str, tuple[str, str, float | None]] = {}  # id -> name, type, quantity
    for s in root.findall(ns + "sample"):
        sid = s.get("id", "")
        name = "" if _GUID.match(sid) else sid
        name = (s.findtext(ns + "description") or "").strip() if not name else name
        q = s.find(ns + "quantity")
        samples[sid] = (name, (s.findtext(ns + "type") or "unkn").strip(), parse_number(q.findtext(ns + "value") or "") if q is not None else None)

    dyes: dict[str, str] = {}
    refs: list[str] = []
    for t in root.findall(ns + "target"):
        dye_el = t.find(ns + "dyeId")
        dye = (dye_el.get("id") or dye_el.text or "").strip() if dye_el is not None else ""
        dyes[t.get("id", "")] = dye
        if t.findtext(ns + "type") == "ref":
            name = _target_name(t.get("id", ""), dye)
            if name != dye and name not in refs:
                refs.append(name)

    reports: list[ImportReport] = []
    for i, run in enumerate(root.iter(ns + "run")):
        reacts = run.findall(ns + "react")
        fmt_el = run.find(ns + "pcrFormat")
        rows = parse_number(fmt_el.findtext(ns + "rows") or "") if fmt_el is not None else None
        cols = parse_number(fmt_el.findtext(ns + "columns") or "") if fmt_el is not None else None
        plate, to_coord = _plate_layout([x.get("id", "").strip() for x in reacts], rows, cols)
        run_id = f"R{first_run_index + i}"
        name = f"{path.stem} · {run.get('id', run_id)}"
        b = ReportBuilder(Run(id=run_id, name=name, source_file=path.name, instrument="rdml", plate_format=plate))
        for react in reacts:
            rid = react.get("id", "").strip()
            sample_el = react.find(ns + "sample")
            sname, stype, quantity = samples.get(sample_el.get("id", "") if sample_el is not None else "", ("", "unkn", None))
            for data in react.findall(ns + "data"):
                b.row()
                try:
                    coord = to_coord(rid)
                except ValueError:
                    b.skip(0, f"bad reaction id {rid!r}")
                    continue
                tar = data.find(ns + "tar")
                tid = tar.get("id", "") if tar is not None else ""
                dye = dyes.get(tid, "")
                role = _ROLES.get(stype, "unknown")
                amplification = _curve(data.findall(ns + "adp"), "cyc", ns)
                excl = (data.findtext(ns + "excl") or "").strip()
                optical = stype == "opt"
                if optical:
                    b.note(f"Well {coord}: optical calibrator, excluded")
                b.add(
                    coord,
                    sname,
                    Reaction(
                        target=_target_name(tid, dye) or dye,
                        fluor=dye,
                        role=role,
                        cq=parse_cq(data.findtext(ns + "cq") or ""),
                        quantity=quantity if role == "std" else None,
                        excluded=optical or bool(excl),
                        exclude_reason="optical calibrator" if optical else excl,
                        amplification=amplification,
                        melt=_curve(data.findall(ns + "mdp"), "tmp", ns),
                        baseline_subtracted=bool(amplification and min(amplification.y) < 0),
                    ),
                )
        b.report.suggested_refs = list(refs)
        reports.append(b.report)
    if not reports:
        raise RdmlError(f"No runs inside RDML file: {path}")
    return reports

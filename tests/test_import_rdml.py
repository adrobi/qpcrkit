import zipfile
from collections import Counter
from pathlib import Path

import pytest

from qpcr_core.importers.detect import import_file
from qpcr_core.importers.rdml import RdmlError, is_rdml, parse_rdml

REAL = Path(__file__).parent / "data" / "real"


def _reactions(rep):
    return [r for w in rep.run.wells.values() for r in w.reactions]


def test_cfx_rdml_with_melt():
    reports = parse_rdml(REAL / "BioRad_qPCR_melt.rdml")
    assert [r.run.id for r in reports] == ["R1", "R2"]
    rx = _reactions(reports[0])
    assert len(rx) == 30 and sum(r.cq is not None for r in rx) == 26
    assert len(rx[0].amplification.x) == 41 and len(rx[0].melt.x) == 61
    assert rx[0].amplification.x[0] == 1.0
    assert rx[0].baseline_subtracted is True
    assert {"ntc", "pos"} <= {r.role for r in rx}
    assert rx[0].target == "EvaGreen" and rx[0].fluor == "FAM"
    assert sum(r.cq is not None for r in _reactions(reports[1])) == 0


def test_lightcycler_multiplex():
    rep = parse_rdml(REAL / "lc96_bACTXY.rdml")[0]
    rx = _reactions(rep)
    assert len(rep.run.wells) == 96 and len(rx) == 384
    assert all(r.cq is not None for r in rx) and len(rx[0].amplification.x) == 50
    assert not any("@" in r.target for r in rx)
    assert {"FAM", "bACT"} & {r.target for r in rx}
    assert "std" in Counter(r.role for r in rx)
    assert rep.run.wells["A1"].reactions[0].target
    assert "Sample 39" in rep.samples


def test_stepone_version_1_0():
    rep = parse_rdml(REAL / "stepone_std.rdml")[0]
    rx = _reactions(rep)
    assert len(rx) == 24 and {r.target for r in rx} == {"RNase P"}
    stds = [r for r in rx if r.role == "std"]
    assert stds and all(r.quantity for r in stds)
    assert 10000.0 in {r.quantity for r in stds}
    assert rep.run.wells["A1"].reactions


def _rdml(tmp_path, xml: str, name="x.rdml"):
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("rdml_data.xml", xml)
    return p


OPT = """<rdml version="1.1">
<sample id="cal"><type>opt</type></sample><sample id="s"><type>nrt</type></sample>
<target id="t"><type>toi</type></target>
<experiment id="e"><run id="r"><react id="1"><sample id="cal"/><data><tar id="t"/><cq>20</cq></data></react>
<react id="2"><sample id="s"/><data><tar id="t"/><cq>30</cq></data></react></run></experiment></rdml>"""


def test_optical_calibrator_excluded_and_nrt(tmp_path):
    rep = parse_rdml(_rdml(tmp_path, OPT))[0]
    a1 = rep.run.wells["A1"].reactions[0]
    assert a1.excluded and a1.exclude_reason == "optical calibrator"
    assert any("optical" in n for n in rep.notes)
    assert rep.run.wells["A2"].reactions[0].role == "nrt"


@pytest.mark.parametrize(
    "xml",
    ['<!DOCTYPE rdml [<!ENTITY a "b">]><rdml/>', "<rdml><broken>", "<rdml version='1.1'></rdml>"],
)
def test_bad_documents_name_the_file(tmp_path, xml):
    with pytest.raises(RdmlError, match="x.rdml"):
        parse_rdml(_rdml(tmp_path, xml))


def test_zip_without_xml_and_not_a_zip(tmp_path):
    p = tmp_path / "x.rdml"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("readme.txt", "hi")
    with pytest.raises(RdmlError, match="x.rdml"):
        parse_rdml(p)
    p.write_bytes(b"not a zip")
    with pytest.raises(ValueError, match="x.rdml"):
        import_file(p, "R1")


def test_import_file_takes_first_run():
    assert is_rdml(REAL / "stepone_std.rdml")
    rep = import_file(REAL / "BioRad_qPCR_melt.rdml", "R7")
    assert rep.run.id == "R7" and rep.run.instrument == "rdml"


def _plate(fmt, ids):
    reacts = "".join(f'<react id="{i}"><sample id="s"/><data><tar id="t"/><cq>20</cq></data></react>' for i in ids)
    return f"""<rdml version="1.1"><sample id="s"><type>unkn</type></sample><target id="t"><type>toi</type></target>
<experiment id="e"><run id="r">{fmt}{reacts}</run></experiment></rdml>"""


def _format(rows, cols):
    return f"<pcrFormat><rows>{rows}</rows><columns>{cols}</columns></pcrFormat>"


def test_48_well_plate_uses_its_own_columns(tmp_path):
    run = parse_rdml(_rdml(tmp_path, _plate(_format(6, 8), [9])))[0].run
    assert list(run.wells) == ["B1"] and run.plate_format == 96


def test_rotor_keeps_positions(tmp_path):
    run = parse_rdml(_rdml(tmp_path, _plate(_format(1, 72), [13])))[0].run
    assert list(run.wells) == ["13"] and run.plate_format == 72


@pytest.mark.parametrize("ids,coord", [([120], "E24"), (["P24"], "P24")])
def test_no_format_recognizes_384(tmp_path, ids, coord):
    run = parse_rdml(_rdml(tmp_path, _plate("", ids)))[0].run
    assert list(run.wells) == [coord] and run.plate_format == 384

from pathlib import Path

from qpcr_core.importers import cfx
from qpcr_core.importers.base import map_role
from qpcr_core.importers.textio import read_rows

DATA = Path(__file__).parent / "data"


def _report():
    return cfx.parse(read_rows(DATA / "cfx_basic.csv"), "cfx_basic.csv", "R1")


def test_sniff():
    assert cfx.sniff(read_rows(DATA / "cfx_basic.csv"))
    assert not cfx.sniff([["Well", "Well Position", "Sample Name", "Target Name", "Task", "CT"]])


def test_coords_and_roles():
    run = _report().run
    assert run.instrument == "cfx"
    assert run.id == "R1"
    assert "A1" in run.wells and "A01" not in run.wells
    std = run.wells["B2"].reactions[0]
    assert (std.role, std.quantity, std.cq) == ("std", 100.0, 21.72)
    ntc = run.wells["A7"].reactions[0]
    assert ntc.role == "ntc" and ntc.cq is None


def test_names_stripped_and_groups():
    rep = _report()
    assert rep.run.wells["A1"].sample == "Ctrl1"
    assert rep.run.wells["A4"].reactions[0].target == "IL6"
    assert rep.samples["Ctrl1"].group == "Ctrl"


def test_broken_row_reported():
    rep = _report()
    assert len(rep.skipped) == 1
    assert rep.skipped[0][0] == 12  # line 12 of the file (header is line 1)
    assert rep.imported + len(rep.skipped) == rep.total_rows == 11


def test_map_role():
    assert map_role("Unkn-03") == "unknown"
    assert map_role("STANDARD") == "std"
    assert map_role("Neg Ctrl") == "ntc"
    assert map_role("NRT") == "nrt"
    assert map_role("Positive Control") == "pos"
    assert map_role("IRC") == "irc"
    assert map_role("whatever") == "unknown"


def test_nrt_role():
    assert map_role("NRT") == "nrt"
    assert map_role("no RT") == "nrt"
    assert map_role("Neg Ctrl") == "ntc"


HEADER = "Well;Fluor;Target;Content;Sample;Cq;Starting Quantity (SQ)\n"


def test_russian_dilution_series(tmp_path):
    from qpcr_core.importers.detect import import_file

    p = tmp_path / "ru.csv"
    p.write_text(
        HEADER + "A01;SYBR;IL6;Std;s;20,5;10,000\nA02;SYBR;IL6;Std;s;21,5;5,000\nA03;SYBR;IL6;Std;s;23,5;0,625\n",
        encoding="utf-8",
    )
    rep = import_file(p, "R1")
    assert [rep.run.wells[c].reactions[0].quantity for c in ("A1", "A2", "A3")] == [10.0, 5.0, 0.625]
    assert rep.run.wells["A1"].reactions[0].cq == 20.5
    assert rep.notes == []


def test_ambiguous_thousands_noted(tmp_path):
    from qpcr_core.importers.detect import import_file

    p = tmp_path / "en.csv"
    p.write_text(
        "Well,Fluor,Target,Content,Sample,Cq,Starting Quantity (SQ)\n"
        'A01,SYBR,IL6,Std,s,20.5,"1,250"\nA02,SYBR,IL6,Std,s,21.5,"2,500"\n',
        encoding="utf-8",
    )
    rep = import_file(p, "R1")
    assert rep.run.wells["A1"].reactions[0].quantity == 1250.0
    assert len(rep.notes) == 1 and "1,250" in rep.notes[0]

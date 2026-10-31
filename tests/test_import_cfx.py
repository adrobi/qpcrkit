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
    assert map_role("NRT") == "ntc"
    assert map_role("Positive Control") == "pos"
    assert map_role("IRC") == "irc"
    assert map_role("whatever") == "unknown"

from pathlib import Path

from qpcr_core.importers import rotorgene
from qpcr_core.importers.textio import read_rows

DATA = Path(__file__).parent / "data"


def _run():
    return rotorgene.parse(read_rows(DATA / "rotorgene_quant.csv"), "rg.csv", "R1").run


def test_sniff():
    assert rotorgene.sniff(read_rows(DATA / "rotorgene_quant.csv"))
    assert not rotorgene.sniff(read_rows(DATA / "cfx_basic.csv"))


def test_positions_and_channels():
    run = _run()
    assert run.instrument == "rotorgene" and run.plate_format == 72
    assert sorted(run.wells, key=int) == ["1", "2", "3", "4", "5", "6"]
    targets = [r.target for r in run.wells["1"].reactions]
    assert targets == ["Green", "Yellow"]
    assert run.wells["6"].reactions[1].cq == 24.0


def test_roles_quantities_missing_ct():
    run = _run()
    std = run.wells["4"].reactions[0]
    assert (std.role, std.quantity) == ("std", 1000.0)
    ntc = run.wells["3"].reactions[0]
    assert ntc.role == "ntc" and ntc.cq is None


def test_no_section_title_uses_default_target():
    rows = [["No.", "Colour", "Name", "Type", "Ct"], ["1", "", "S", "Unknown", "20"]]
    assert rotorgene.parse(rows, "x", "R1").run.wells["1"].reactions[0].target == "Target1"


def test_given_conc_with_thousands():
    rows = [["No.", "Colour", "Name", "Type", "Ct", "Given Conc (copies)"], ["1", "", "S", "Standard", "20", "1,000.5"]]
    assert rotorgene.parse(rows, "x", "R1").run.wells["1"].reactions[0].quantity == 1000.5

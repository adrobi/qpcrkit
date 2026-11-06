from pathlib import Path

from qpcr_core.importers import quantstudio
from qpcr_core.importers.textio import read_rows

DATA = Path(__file__).parent / "data"


def _rep(name):
    return quantstudio.parse(read_rows(DATA / name), name, "R1")


def test_sniff():
    assert quantstudio.sniff(read_rows(DATA / "qs_results.txt"))
    assert quantstudio.sniff(read_rows(DATA / "qs7500_384_numeric.txt"))
    assert not quantstudio.sniff(read_rows(DATA / "cfx_basic.csv"))


def test_results_table():
    rep = _rep("qs_results.txt")
    run = rep.run
    assert run.instrument == "quantstudio" and run.plate_format == 96
    omitted = run.wells["A2"].reactions[0]
    assert omitted.excluded and omitted.exclude_reason == "omitted in instrument"
    assert run.wells["A3"].reactions[0].role == "ntc"
    assert run.wells["A3"].reactions[0].cq is None
    std = run.wells["B1"].reactions[0]
    assert (std.role, std.cq, std.quantity) == ("std", 18.4, 1000.0)
    assert rep.samples["Ctrl1"].group == "Ctrl"
    assert run.wells["A1"].reactions[0].fluor == "SYBR"


def test_numeric_wells_on_384_block():
    run = _rep("qs7500_384_numeric.txt").run
    assert run.plate_format == 384
    assert run.wells["B1"].reactions[0].cq == 24.5
    assert run.wells["B2"].sample == "S1"


def test_cq_header_variants():
    for name in ("CT", "Ct", "Cq"):
        rows = [["Well", "Sample Name", "Target Name", "Task", name], ["A1", "s", "t", "UNKNOWN", "20.0"]]
        assert quantstudio.parse(rows, "x", "R1").run.wells["A1"].reactions[0].cq == 20.0


def test_sample_setup_section_before_results():
    rows = [
        ["* Block Type = 96-Well Block (0.2mL)"],
        ["[Sample Setup]"],
        ["Well", "Well Position", "Sample Name", "Target Name", "Task", "Reporter"],
        ["1", "A1", "s1", "IL6", "UNKNOWN", "SYBR"],
        ["[Results]"],
        ["Well", "Well Position", "Sample Name", "Target Name", "Task", "Reporter", "CT"],
        ["1", "A1", "s1", "IL6", "UNKNOWN", "SYBR", "22.5"],
    ]
    assert quantstudio.sniff(rows)
    run = quantstudio.parse(rows, "x", "R1").run
    assert run.wells["A1"].reactions[0].cq == 22.5
    assert len(run.wells["A1"].reactions) == 1


def test_crt_header():
    rows = [["Well", "Sample Name", "Target Name", "Task", "CRT"], ["A1", "s", "t", "UNKNOWN", "20.0"]]
    assert quantstudio.sniff(rows)
    assert quantstudio.parse(rows, "x", "R1").run.wells["A1"].reactions[0].cq == 20.0


RESULTS = [
    ["Well", "Well Position", "Sample", "Target", "Task", "Cq", "Quantity"],
    ["1", "A1", "Std", "IL6", "STANDARD", "20.0", "N/A"],
    ["2", "A2", "Std", "IL6", "STANDARD", "23.3", "N/A"],
]


def test_quantity_placeholder_falls_back_to_other_sheet():
    sheet = [["Well Position", "Target", "Task", "Quantity"], ["A01", "IL6", "STANDARD", "1000"], ["A02", "IL6", "STANDARD", "100"]]
    rep = quantstudio.parse(RESULTS, "x", "R1", sheets={"Standard Curve Result": sheet})
    assert rep.run.wells["A1"].reactions[0].quantity == 1000.0
    assert rep.run.wells["A2"].reactions[0].quantity == 100.0


def test_replicate_sheet_compares_numbers_not_text():
    sheet = [["Sample", "Target", "Quantity"], ["Std", "IL6", "100"], ["Std", "IL6", "100.0"]]
    rep = quantstudio.parse(RESULTS, "x", "R1", sheets={"Replicate Group Result": sheet})
    assert rep.run.wells["A1"].reactions[0].quantity == 100.0


def test_ambiguous_replicate_sheet_gives_no_quantity():
    sheet = [["Sample", "Target", "Quantity"], ["Std", "IL6", "100"], ["Std", "IL6", "10"]]
    rep = quantstudio.parse(RESULTS, "x", "R1", sheets={"Replicate Group Result": sheet})
    assert rep.run.wells["A1"].reactions[0].quantity is None


def test_footer_with_three_cells_is_not_a_skipped_row():
    rows = [["Well", "Sample Name", "Target Name", "Task", "CT"], ["A1", "s", "t", "UNKNOWN", "20"], ["Analysis", "Type", "Single"]]
    rep = quantstudio.parse(rows, "x", "R1")
    assert rep.skipped == [] and rep.total_rows == 1


def test_bad_coordinate_with_data_is_reported():
    rows = [["Well", "Sample Name", "Target Name", "Task", "CT"], ["??", "s", "t", "UNKNOWN", "20"]]
    assert len(quantstudio.parse(rows, "x", "R1").skipped) == 1

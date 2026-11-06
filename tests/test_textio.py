import openpyxl
import pytest

from qpcr_core.importers.textio import parse_cq, parse_number, read_rows


def test_utf8_bom_comma(tmp_path):
    p = tmp_path / "a.csv"
    p.write_bytes("﻿Well,Cq\nA1,20.5\n".encode("utf-8"))
    assert read_rows(p) == [["Well", "Cq"], ["A1", "20.5"]]


def test_utf16_tab(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("Well\tCq\nA1\t20.5\n", encoding="utf-16")
    assert read_rows(p) == [["Well", "Cq"], ["A1", "20.5"]]


def test_cp1251_semicolon_decimal_comma(tmp_path):
    p = tmp_path / "a.csv"
    p.write_bytes("Лунка;Образец;Cq\nA1;Контроль 1;20,5\nA2; Контроль 2 ;21,0\n".encode("cp1251"))
    rows = read_rows(p)
    assert rows[1] == ["A1", "Контроль 1", "20,5"]
    assert rows[2][1] == "Контроль 2"
    assert parse_cq(rows[1][2]) == 20.5


def test_preamble_does_not_confuse_delimiter(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("Experiment: demo, run 1\n\nWell,Target,Cq\nA1,IL6,20.1\nA2,IL6,20.2\n", encoding="utf-8")
    rows = read_rows(p)
    assert ["Well", "Target", "Cq"] in rows


def _xlsx(path, sheets):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets:
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    wb.save(path)


def test_xlsx_prefers_results_sheet(tmp_path):
    p = tmp_path / "a.xlsx"
    _xlsx(p, [("Info", [["x"]]), ("Results", [["Well", "CT"], ["A1", 20.123456789], ["A2", None]])])
    assert read_rows(p) == [["Well", "CT"], ["A1", "20.123456789"], ["A2", ""]]


def test_xlsx_first_sheet_without_results(tmp_path):
    p = tmp_path / "a.xlsx"
    _xlsx(p, [("0", [["Well", "Cq"], ["A1", 21]]), ("Other", [["y"]])])
    assert read_rows(p) == [["Well", "Cq"], ["A1", "21"]]


def test_parse_number():
    assert parse_number("1,5e3") == 1500.0
    assert parse_number(" 2.5 ") == 2.5
    assert parse_number("") is None
    assert parse_number("abc") is None


@pytest.mark.parametrize("s", ["Undetermined", "N/A", "NaN", "No Ct", "—", "-", "", "undetermined"])
def test_parse_cq_missing(s):
    assert parse_cq(s) is None


def test_parse_cq_value():
    assert parse_cq("23,45") == 23.45


from qpcr_core.importers.textio import UnsupportedFileError, detect_number_style, read_sheets, read_table


@pytest.mark.parametrize(
    "cells,delim,expected",
    [
        (["10,000", "5,000", "2,500", "1,250", "0,625"], None, ("decimal_comma", False)),
        (["1,250.000", "100,000,000.000"], None, ("thousands_comma", False)),
        (["100,000,000"], None, ("thousands_comma", False)),
        (["23,45"], None, ("decimal_comma", False)),
        (["1,250", "2,500"], ";", ("decimal_comma", False)),
        (["1,250", "2,500"], ",", ("thousands_comma", True)),
        (["1.250,5"], None, ("decimal_comma", False)),
        (["1000", "10", ""], None, ("decimal_comma", False)),
    ],
)
def test_detect_number_style(cells, delim, expected):
    assert detect_number_style(cells, delim) == expected


def test_parse_number_styles():
    assert parse_number("1,250.000", "thousands_comma") == 1250.0
    assert parse_number("100,000,000", "thousands_comma") == 1e8
    assert parse_number("1,250", "decimal_comma") == 1.25
    assert parse_number("1.250,5", "decimal_comma") == 1250.5
    assert parse_number("1 250,5") == 1250.5
    assert parse_number("1\u00a0250,5") == 1250.5
    assert parse_number("1,5e3") == 1500.0


def test_binary_files_rejected(tmp_path):
    p = tmp_path / "run.pcrd"
    p.write_bytes(b"PK\x03\x04\x00\x00binary")
    with pytest.raises(UnsupportedFileError, match="run.pcrd"):
        read_rows(p)
    q = tmp_path / "strange.csv"
    q.write_bytes(b"a,b\x00,c\n")
    with pytest.raises(UnsupportedFileError):
        read_rows(q)


def test_read_table_reports_delimiter(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("x;y\n1;2\n", encoding="utf-8")
    assert read_table(p) == ([["x", "y"], ["1", "2"]], ";")


def test_read_sheets(tmp_path):
    p = tmp_path / "a.xlsx"
    _xlsx(p, [("Results", [["Well"], ["A1"]]), ("Other", [["z"]])])
    assert read_sheets(p) == {"Results": [["Well"], ["A1"]], "Other": [["z"]]}
    t = tmp_path / "a.txt"
    t.write_text("q\tw\n", encoding="utf-8")
    assert read_sheets(t) == {"": [["q", "w"]]}


def test_both_separators_decide_by_their_order():
    assert parse_number("1,250.0") == 1250.0
    assert parse_number("1.250,5", "thousands_comma") == 1250.5


def test_thousands_style_keeps_real_decimals():
    assert parse_number("0,5", "thousands_comma") == 0.5
    assert parse_number("23,45", "thousands_comma") == 23.45
    assert parse_number("1,250", "thousands_comma") == 1250.0


@pytest.mark.parametrize("delim", [None, ";"])
def test_plain_decimals_settle_the_comma(delim):
    assert detect_number_style(["1,000", "500", "12.5"], delim) == ("thousands_comma", False)

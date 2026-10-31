import sys

import qpcr_core
from ui.errors import format_report


def test_format_report():
    try:
        raise ValueError("bad data")
    except ValueError:
        text = format_report(sys.exc_info())
    assert "ValueError" in text and "bad data" in text
    assert qpcr_core.__version__ in text and "Python" in text

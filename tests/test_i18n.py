import i18n
from i18n import RU, set_language, tr
from translations_en import EN


def test_keysets_match():
    assert set(RU) == set(EN)


def test_tr_formats():
    set_language("en")
    assert "0.41" in tr("qc.rep_sd_high", sd=0.41, limit=0.3)


def test_unknown_key_returns_key():
    assert tr("nope") == "nope"


def test_current_language():
    set_language("ru")
    assert i18n.current_language() == "ru"
    set_language("en")

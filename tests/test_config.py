import json

from qpcr_core.config import AppConfig, load_config, save_config
from qpcr_core.importers.generic_csv import ColumnMapping


def test_round_trip(tmp_path):
    path = tmp_path / "c.json"
    cfg = AppConfig(theme="dark", language="ru", recent=["a.qpcrkit.json"],
                    csv_presets={"lab": ColumnMapping(well="Pos", target="Gene", cq="Ct").to_dict()})
    save_config(cfg, path)
    assert load_config(path) == cfg
    assert ColumnMapping.from_dict(load_config(path).csv_presets["lab"]).cq == "Ct"


def test_add_recent_dedup_and_limit():
    cfg = AppConfig()
    for p in ["a", "b", "a", "a"]:
        cfg.add_recent(p)
    assert cfg.recent == ["a", "b"]
    for i in range(20):
        cfg.add_recent(f"f{i}", max_items=5)
    assert len(cfg.recent) == 5 and cfg.recent[0] == "f19"


def test_missing_or_broken(tmp_path):
    assert load_config(tmp_path / "none.json") == AppConfig()
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    assert load_config(bad) == AppConfig()


def test_unknown_keys_ignored(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"language": "ru", "future": 1}), encoding="utf-8")
    assert load_config(p) == AppConfig(language="ru")


def test_old_dark_setting_migrates(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"dark": True}), encoding="utf-8")
    assert load_config(p).theme == "dark"
    p.write_text(json.dumps({"dark": False}), encoding="utf-8")
    assert load_config(p).theme == "auto"
    p.write_text(json.dumps({"theme": "light", "dark": True}), encoding="utf-8")
    assert load_config(p).theme == "light"

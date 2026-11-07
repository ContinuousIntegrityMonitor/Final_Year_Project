"""Config border smoke tests."""

from cim.common.config import load_config


def test_load_config_defaults() -> None:
    cfg = load_config()
    assert cfg.log_level == "INFO"
    assert cfg.store_path.name == "cim-store.sqlite"

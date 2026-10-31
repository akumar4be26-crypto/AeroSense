import shutil
from pathlib import Path

import pytest
import yaml

from app.core.config import ConfigError, default_config_dir, load_config


@pytest.fixture
def cfg_dir(tmp_path: Path) -> Path:
    dst = tmp_path / "config"
    shutil.copytree(default_config_dir(), dst)
    return dst


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def test_real_config_loads():
    cfg = load_config()
    assert cfg.settings.default_location.city == "Patiala"
    assert cfg.settings.forecast.durations_hours == [24, 48, 72]
    assert cfg.model.candidates["xgboost"].params["n_estimators"] == 500
    assert cfg.simulation.calibration_status == "illustrative_uncalibrated"
    assert set(cfg.aqi.pollutants) >= {"pm25", "pm10", "no2", "so2", "co", "o3", "nh3", "pb"}


def test_aqi_category_ranges_are_cpcb():
    cfg = load_config()
    assert [(c.name, c.min, c.max) for c in cfg.aqi.categories] == [
        ("Good", 0, 50), ("Satisfactory", 51, 100), ("Moderate", 101, 200),
        ("Poor", 201, 300), ("Very Poor", 301, 400), ("Severe", 401, 500),
    ]


def test_missing_file_is_reported(cfg_dir: Path):
    (cfg_dir / "settings.yaml").unlink()
    with pytest.raises(ConfigError, match="settings.yaml"):
        load_config(cfg_dir)


def test_invalid_coordinates_rejected(cfg_dir: Path):
    _edit(cfg_dir / "settings.yaml", lambda d: d["default_location"].update(latitude=123))
    with pytest.raises(ConfigError, match="latitude"):
        load_config(cfg_dir)


def test_silent_demo_fallback_cannot_be_enabled(cfg_dir: Path):
    _edit(cfg_dir / "settings.yaml", lambda d: d["data_mode"].update(allow_silent_fallback=True))
    with pytest.raises(ConfigError, match="allow_silent_fallback"):
        load_config(cfg_dir)


def test_simulator_default_must_be_within_range(cfg_dir: Path):
    _edit(cfg_dir / "simulation_config.yaml", lambda d: d["parameters"]["wind_speed"].update(default=99))
    with pytest.raises(ConfigError, match="min <= default <= max"):
        load_config(cfg_dir)


def test_non_increasing_breakpoints_rejected(cfg_dir: Path):
    _edit(cfg_dir / "aqi_breakpoints.yaml", lambda d: d["pollutants"]["pm25"].update(c_hi=[30, 20, 90, 120, 250, None]))
    with pytest.raises(ConfigError, match="strictly increasing"):
        load_config(cfg_dir)


def test_selection_metric_must_be_listed(cfg_dir: Path):
    _edit(cfg_dir / "model_config.yaml", lambda d: d.update(selection_metric="bogus"))
    with pytest.raises(ConfigError, match="selection_metric"):
        load_config(cfg_dir)


def test_non_https_provider_rejected(cfg_dir: Path):
    _edit(cfg_dir / "data_sources.yaml", lambda d: d["weather"][0].update(base_url="http://insecure.example"))
    with pytest.raises(ConfigError, match="HTTPS"):
        load_config(cfg_dir)

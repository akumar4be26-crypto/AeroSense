import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException

from app.core.config import load_config
from app.ml import pipeline
from app.ml.aqi import aqi_from_hourly, compute_aqi, sub_index

CFG = load_config()


@pytest.mark.parametrize("pollutant,conc,expected", [("pm25", 30, 50), ("pm25", 60, 100), ("pm25", 45, 75.5), ("pm10", 100, 100)])
def test_sub_index_known_values(pollutant, conc, expected):
    assert sub_index(CFG.aqi, pollutant, conc) == pytest.approx(expected, abs=1)


def test_sub_index_capped_at_500():
    assert sub_index(CFG.aqi, "pm25", 10_000) == 500


def test_aqi_requires_enough_pollutants():
    result = compute_aqi(CFG.aqi, {"pm25": 60, "no2": None, "o3": None})
    assert result["aqi"] is None and result["reason"]


def test_aqi_picks_dominant_pollutant():
    result = compute_aqi(CFG.aqi, {"pm25": 30, "pm10": 300, "no2": 20})
    assert result["dominant_pollutant"] == "pm10"
    assert result["category"] == "Poor"


def test_hourly_coverage_rule():
    sparse = [None] * 20 + [50.0] * 4  # only 4 of 24 hourly values
    result = aqi_from_hourly(CFG.aqi, {"pm25": sparse, "pm10": sparse, "no2": sparse})
    assert result["aqi"] is None


def _air_weather(hours: int):
    rng = np.random.default_rng(0)
    times = pd.date_range("2026-01-01", periods=hours, freq="h")
    base = 80 + 40 * np.sin(np.arange(hours) / 24 * 2 * np.pi) + rng.normal(0, 5, hours)
    iso = [t.strftime("%Y-%m-%dT%H:%M") for t in times]
    air = {"data": {"current": {"time": iso[-1]}, "hourly": {
        "time": iso, "pm2_5": list(base), "pm10": list(base * 2), "nitrogen_dioxide": list(base / 3),
        "sulphur_dioxide": list(base / 5), "carbon_monoxide": list(base * 8), "ozone": list(base / 2)}}}
    wx = {"data": {"hourly": {
        "time": iso, "temperature_2m": list(20 + base / 10), "relative_humidity_2m": [60.0] * hours,
        "wind_speed_10m": [8.0] * hours, "wind_direction_10m": [180.0] * hours,
        "surface_pressure": [1000.0] * hours, "rain": [0.0] * hours}}}
    return air, wx


def _fast_config():
    cfg = CFG.model_copy(deep=True)
    cfg.model.validation.cv_folds = 2
    cfg.model.candidates["random_forest"].params = {"n_estimators": 10, "max_depth": 4, "n_jobs": 1}
    cfg.model.candidates["xgboost"].enabled = False
    cfg.model.horizons_hours = [24]
    cfg.model.targets = ["aqi", "pm25"]
    return cfg


def test_train_and_predict_roundtrip(tmp_path):
    cfg = _fast_config()
    air, wx = _air_weather(1000)
    frame = pipeline.build_frame(cfg, air, wx)
    meta = pipeline.train_location(cfg, frame, tmp_path)
    assert set(meta["results"]) == {"aqi_24h", "pm25_24h"}
    assert "firecracker_activity" in meta["unavailable_features"]
    assert meta["data_class"] == "MODELLED_ESTIMATE"
    out = pipeline.predict(cfg, frame, tmp_path)
    assert out["forecasts"]["aqi"][0]["horizon_hours"] == 24


def test_training_refused_below_minimum_rows(tmp_path):
    cfg = _fast_config()
    air, wx = _air_weather(200)
    frame = pipeline.build_frame(cfg, air, wx)
    with pytest.raises(HTTPException) as exc:
        pipeline.train_location(cfg, frame, tmp_path)
    assert exc.value.status_code == 422
    assert pipeline.load_metadata(tmp_path) is None


def test_predict_without_model_is_conflict(tmp_path):
    air, wx = _air_weather(200)
    frame = pipeline.build_frame(CFG, air, wx)
    with pytest.raises(HTTPException) as exc:
        pipeline.predict(CFG, frame, tmp_path)
    assert exc.value.status_code == 409

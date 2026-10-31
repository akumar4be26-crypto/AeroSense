"""Local training and prediction on provider history. Everything is driven by config/model_config.yaml."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from fastapi import HTTPException
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit

from app.core.config import AppConfig, default_config_dir
from app.ml.aqi import PROVIDER_TO_CPCB, aqi_series, category_for

WEATHER_COLUMNS = {
    "temperature_2m": "temperature",
    "relative_humidity_2m": "humidity",
    "wind_speed_10m": "wind_speed",
    "wind_direction_10m": "wind_direction",
    "surface_pressure": "pressure",
    "rain": "rainfall",
}
HISTORY_TARGETS = ("aqi", "pm25", "pm10")  # series that receive lag / rolling features
MAX_PAST_DAYS = 92  # Open-Meteo limit
PREDICT_PAST_DAYS = 7

TRAIN_LOCK = threading.Lock()


def location_key(latitude: float, longitude: float) -> str:
    return f"{latitude:.2f}_{longitude:.2f}"


def artifacts_dir(config: AppConfig, key: str) -> Path:
    return default_config_dir().parent / config.model.artifacts_dir / key


def build_frame(config: AppConfig, air: dict[str, Any], weather: dict[str, Any]) -> pd.DataFrame:
    """Observed hourly frame (provider future hours removed) with CPCB pollutant, weather and AQI columns."""
    def to_frame(payload: dict[str, Any], rename: dict[str, str]) -> pd.DataFrame:
        hourly = payload["data"]["hourly"]
        frame = pd.DataFrame({new: hourly.get(old) for old, new in rename.items()})
        frame.index = pd.to_datetime(hourly["time"])
        return frame.apply(pd.to_numeric, errors="coerce")

    pollutants = to_frame(air, PROVIDER_TO_CPCB)
    weather_frame = to_frame(weather, WEATHER_COLUMNS)
    frame = pollutants.join(weather_frame, how="inner").sort_index()
    cutoff = pd.to_datetime(air["data"].get("current", {}).get("time"))
    if pd.notna(cutoff):
        frame = frame[frame.index <= cutoff]
    frame["aqi"] = aqi_series(config.aqi, frame)
    return frame


def make_features(config: AppConfig, frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Feature matrix. Activity and Diwali features have no observed source and are never fabricated."""
    cfg = config.model.features
    features = pd.DataFrame(index=frame.index)
    for column in cfg.historical_pollution + cfg.weather:
        if column == "wind_direction":
            radians = np.deg2rad(frame[column])
            features["wind_direction_sin"] = np.sin(radians)
            features["wind_direction_cos"] = np.cos(radians)
        else:
            features[column] = frame[column]
    for column in HISTORY_TARGETS:
        for lag in cfg.lag_hours:
            features[f"{column}_lag{lag}"] = frame[column].shift(lag)
        for window in cfg.rolling_windows_hours:
            features[f"{column}_roll{window}"] = frame[column].rolling(window, min_periods=window).mean()
    temporal = {
        "hour": frame.index.hour,
        "day": frame.index.day,
        "month": frame.index.month,
        "day_of_week": frame.index.day_of_week,
    }
    for name in cfg.temporal:
        if name in temporal:
            features[name] = temporal[name]
    features["hour_sin"] = np.sin(2 * np.pi * frame.index.hour / 24)
    features["hour_cos"] = np.cos(2 * np.pi * frame.index.hour / 24)
    used = list(features.columns)
    return features, used


def unavailable_features(config: AppConfig) -> list[str]:
    cfg = config.model.features
    return cfg.activity_indices + [t for t in cfg.temporal if t in ("diwali_proximity_days", "days_since_diwali")] + [
        p for p in cfg.historical_pollution if p in ("nh3", "pb")
    ]


def _metrics(names: list[str], y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    out: dict[str, float] = {}
    for name in names:
        if name == "mae":
            out[name] = float(mean_absolute_error(y_true, y_pred))
        elif name == "rmse":
            out[name] = float(np.sqrt(mean_squared_error(y_true, y_pred)))
        elif name == "r2":
            out[name] = float(r2_score(y_true, y_pred)) if len(y_true) > 1 else float("nan")
        elif name == "mape":
            mask = y_true > 1e-6
            out[name] = float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100) if mask.any() else float("nan")
    return out


def available_candidates(config: AppConfig) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Enabled model factories plus honest notes for candidates that could not be used."""
    seed = config.model.random_seed
    factories: dict[str, Any] = {}
    skipped: dict[str, str] = {}
    for name, spec in config.model.candidates.items():
        if not spec.enabled:
            continue
        if name == "persistence":
            factories[name] = None
        elif name == "random_forest":
            factories[name] = lambda p=dict(spec.params): RandomForestRegressor(random_state=seed, **p)
        elif name == "xgboost":
            try:
                from xgboost import XGBRegressor  # noqa: PLC0415 - optional native dependency
            except Exception as exc:  # noqa: BLE001 - e.g. missing libomp on macOS
                reason = next((line for line in str(exc).splitlines() if line.strip()), type(exc).__name__)
                skipped[name] = f"xgboost unavailable in this environment: {reason.strip()[:160]}"
                continue
            factories[name] = lambda p=dict(spec.params), cls=XGBRegressor: cls(**{"random_state": seed, **p})
        else:
            skipped[name] = "unknown candidate"
    return factories, skipped


def train_location(config: AppConfig, frame: pd.DataFrame, out_dir: Path, meta_extra: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config.model
    features, columns = make_features(config, frame)
    factories, skipped = available_candidates(config)
    split_fraction = cfg.split.train_fraction
    results: dict[str, Any] = {}
    deployed: dict[str, Any] = {}
    n_rows = 0

    for target in cfg.targets:
        for horizon in cfg.horizons_hours:
            key = f"{target}_{horizon}h"
            data = features.copy()
            data["__y"] = frame[target].shift(-horizon)
            data["__persist"] = frame[target]
            data = data.dropna()
            n_rows = max(n_rows, len(data))
            if len(data) < cfg.min_training_rows:
                raise HTTPException(
                    status_code=422,
                    detail=f"Only {len(data)} usable hourly rows for {key}; at least {cfg.min_training_rows} are required.",
                )
            cut = int(len(data) * split_fraction)
            train, test = data.iloc[:cut], data.iloc[cut:]
            x_train, y_train = train[columns].to_numpy(), train["__y"].to_numpy()
            x_test, y_test = test[columns].to_numpy(), test["__y"].to_numpy()
            candidate_results: dict[str, Any] = {}

            for name, factory in factories.items():
                if factory is None:
                    pred = test["__persist"].to_numpy()
                    cv_rmse = float(np.sqrt(np.mean((train["__persist"].to_numpy() - y_train) ** 2)))
                else:
                    model = factory()
                    model.fit(x_train, y_train)
                    pred = model.predict(x_test)
                    errors = []
                    for fit_idx, val_idx in TimeSeriesSplit(n_splits=cfg.validation.cv_folds).split(x_train):
                        fold = factory()
                        fold.fit(x_train[fit_idx], y_train[fit_idx])
                        errors.append(np.sqrt(np.mean((fold.predict(x_train[val_idx]) - y_train[val_idx]) ** 2)))
                    cv_rmse = float(np.mean(errors))
                candidate_results[name] = {"metrics": _metrics(cfg.metrics, y_test, pred), "cv_rmse": cv_rmse}

            metric = cfg.selection_metric
            best = min(candidate_results, key=lambda n: candidate_results[n]["metrics"][metric])
            baseline = candidate_results["persistence"]["metrics"][metric]
            chosen = candidate_results[best]["metrics"][metric]
            skill = None if baseline == 0 else float(1 - chosen / baseline)
            if best == "persistence":
                deployed[key] = None
            else:
                final = factories[best]()
                final.fit(data[columns].to_numpy(), data["__y"].to_numpy())  # refit on all rows for deployment
                deployed[key] = final
            results[key] = {
                "selected": best,
                "skill_vs_persistence": skill,
                "train_rows": int(len(train)),
                "test_rows": int(len(test)),
                "candidates": candidate_results,
            }

    metadata = {
        "model_version": cfg.model_version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_rows": n_rows,
        "training_start": str(frame.index.min()),
        "training_end": str(frame.index.max()),
        "data_class": "MODELLED_ESTIMATE",
        "data_note": "Trained locally on CAMS-modelled hourly history from the air-quality provider, not on sensor readings.",
        "selection_metric": cfg.selection_metric,
        "feature_columns": columns,
        "unavailable_features": unavailable_features(config),
        "skipped_candidates": skipped,
        "results": results,
        **(meta_extra or {}),
    }
    _save(out_dir, {"models": deployed, "feature_columns": columns}, metadata)
    return metadata


def _atomic_write(path: Path, writer) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    os.close(fd)
    try:
        writer(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _save(out_dir: Path, bundle: dict[str, Any], metadata: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(out_dir / "bundle.joblib", lambda p: joblib.dump(bundle, p))
    _atomic_write(out_dir / "metadata.json", lambda p: Path(p).write_text(json.dumps(metadata, indent=2, default=str)))


def load_metadata(out_dir: Path) -> dict[str, Any] | None:
    path = out_dir / "metadata.json"
    if not path.exists() or not (out_dir / "bundle.joblib").exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def predict(config: AppConfig, frame: pd.DataFrame, out_dir: Path) -> dict[str, Any]:
    metadata = load_metadata(out_dir)
    if metadata is None:
        raise HTTPException(status_code=409, detail="No locally trained model for this location. Train one first.")
    bundle = joblib.load(out_dir / "bundle.joblib")
    features, _ = make_features(config, frame)
    row = features[bundle["feature_columns"]].iloc[[-1]]
    if row.isna().any(axis=None):
        raise HTTPException(status_code=502, detail="Not enough recent provider history to build prediction features.")
    base_time = frame.index[-1]
    forecasts: dict[str, list[dict[str, Any]]] = {}
    for target in config.model.targets:
        points = []
        for horizon in config.model.horizons_hours:
            key = f"{target}_{horizon}h"
            model = bundle["models"].get(key)
            value = float(frame[target].iloc[-1]) if model is None else float(model.predict(row.to_numpy())[0])
            value = max(0.0, value)
            point = {
                "horizon_hours": horizon,
                "time": str(base_time + pd.Timedelta(hours=horizon)),
                "value": round(value, 1),
                "model": metadata["results"][key]["selected"],
            }
            if target == "aqi":
                point["category"] = category_for(config.aqi, min(value, 500))
            points.append(point)
        forecasts[target] = points
    return {"base_time": str(base_time), "forecasts": forecasts, "metadata_summary": summarise(metadata)}


def summarise(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_version": metadata["model_version"],
        "trained_at": metadata["trained_at"],
        "training_rows": metadata["training_rows"],
        "training_start": metadata["training_start"],
        "training_end": metadata["training_end"],
        "data_class": metadata["data_class"],
        "data_note": metadata["data_note"],
        "unavailable_features": metadata["unavailable_features"],
        "skipped_candidates": metadata["skipped_candidates"],
        "results": {
            key: {
                "selected": value["selected"],
                "skill_vs_persistence": value["skill_vs_persistence"],
                "metrics": value["candidates"][value["selected"]]["metrics"],
                "persistence_metrics": value["candidates"]["persistence"]["metrics"],
            }
            for key, value in metadata["results"].items()
        },
    }

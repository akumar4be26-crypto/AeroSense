from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import AppConfig, get_config
from app.core.env import get_env
from app.database.session import get_session
from app.ml import pipeline
from app.ml.aqi import PROVIDER_TO_CPCB, aqi_from_hourly
from app.services.activity import get_activity
from app.services.diversion import get_diversion
from app.services.environmental import get_observations, simulate
from app.schemas.common import HealthResponse

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(session: Session = Depends(get_session), config: AppConfig = Depends(get_config)) -> HealthResponse:
    try:
        session.execute(text("SELECT 1"))
        db = "ok"
    except Exception:  # noqa: BLE001 - health must report, not raise
        db = "unavailable"
    return HealthResponse(
        status="ok" if db == "ok" else "degraded",
        app=config.settings.app.name,
        version=config.settings.app.version,
        environment=get_env().environment,
        time=datetime.now(timezone.utc),
        database=db,
        config_valid=True,
    )


@router.get("/config/public", tags=["system"])
def public_config(config: AppConfig = Depends(get_config)) -> dict:
    """Non-secret settings the frontend needs, so GPS/map/forecast options stay centralised in YAML."""
    s = config.settings
    return {
        "app": s.app.model_dump(),
        "default_location": s.default_location.model_dump(),
        "forecast": s.forecast.model_dump(),
        "gps": s.gps.model_dump(),
        "refresh": {"api_refresh_interval_seconds": s.refresh.api_refresh_interval_seconds},
        "data_mode": s.data_mode.model_dump(),
        "map": s.map.model_dump(),
        "simulator": {
            "calibration_status": config.simulation.calibration_status,
            "parameters": {k: v.model_dump() for k, v in config.simulation.parameters.items()},
        },
        "aqi_categories": [category.model_dump() for category in config.aqi.categories],
    }


@router.get("/air-quality", tags=["environment"])
def air_quality(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    config: AppConfig = Depends(get_config),
) -> dict:
    return get_observations(config, get_env(), "air_quality", latitude, longitude)


@router.get("/weather", tags=["environment"])
def weather(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    config: AppConfig = Depends(get_config),
) -> dict:
    return get_observations(config, get_env(), "weather", latitude, longitude)


@router.post("/simulation", tags=["environment"])
def simulation(
    values: dict[str, float] = Body(...),
    config: AppConfig = Depends(get_config),
) -> dict:
    return simulate(config, values)


def _history(config: AppConfig, latitude: float, longitude: float, past_days: int):
    env = get_env()
    air = get_observations(config, env, "air_quality", latitude, longitude, past_days=past_days, forecast_days=1)
    wx = get_observations(config, env, "weather", latitude, longitude, past_days=past_days, forecast_days=1)
    return air, pipeline.build_frame(config, air, wx)


@router.get("/aqi", tags=["environment"])
def aqi(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    config: AppConfig = Depends(get_config),
) -> dict:
    air = get_observations(config, get_env(), "air_quality", latitude, longitude, past_days=2, forecast_days=1)
    hourly = air["data"]["hourly"]
    cutoff = air["data"].get("current", {}).get("time")
    times = hourly["time"]
    end = times.index(cutoff) + 1 if cutoff in times else len(times)
    series = {cpcb: hourly[prov][:end] for prov, cpcb in PROVIDER_TO_CPCB.items() if prov in hourly}
    result = aqi_from_hourly(config.aqi, series)
    return {
        **result,
        "as_of": cutoff,
        "provider": air["provider"],
        "data_class": air["data_class"],
        "label": "Estimated CPCB-method AQI computed from modelled data; not an official CPCB station reading.",
    }


@router.get("/ml/status", tags=["ml"])
def ml_status(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    config: AppConfig = Depends(get_config),
) -> dict:
    meta = pipeline.load_metadata(pipeline.artifacts_dir(config, pipeline.location_key(latitude, longitude)))
    return {"trained": meta is not None, "model": pipeline.summarise(meta) if meta else None}


@router.post("/ml/train", tags=["ml"])
def ml_train(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    config: AppConfig = Depends(get_config),
) -> dict:
    if not pipeline.TRAIN_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Training is already running")
    try:
        _, frame = _history(config, latitude, longitude, pipeline.MAX_PAST_DAYS)
        key = pipeline.location_key(latitude, longitude)
        meta = pipeline.train_location(
            config, frame, pipeline.artifacts_dir(config, key), {"latitude": latitude, "longitude": longitude}
        )
        return {"trained": True, "model": pipeline.summarise(meta)}
    finally:
        pipeline.TRAIN_LOCK.release()


@router.get("/ml/forecast", tags=["ml"])
def ml_forecast(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    config: AppConfig = Depends(get_config),
) -> dict:
    out_dir = pipeline.artifacts_dir(config, pipeline.location_key(latitude, longitude))
    if pipeline.load_metadata(out_dir) is None:
        raise HTTPException(status_code=409, detail="No locally trained model for this location. Train one first.")
    _, frame = _history(config, latitude, longitude, pipeline.PREDICT_PAST_DAYS)
    return pipeline.predict(config, frame, out_dir)


@router.get("/diversion", tags=["traffic"])
def diversion(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    config: AppConfig = Depends(get_config),
) -> dict:
    return get_diversion(config, get_env(), latitude, longitude)


@router.get("/activity", tags=["health"])
def activity(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    config: AppConfig = Depends(get_config),
) -> dict:
    return get_activity(config, get_env(), latitude, longitude)

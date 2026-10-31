from __future__ import annotations

import math
from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import AppConfig, Provider
from app.core.env import EnvSettings


def _provider(config: AppConfig, group: str) -> Provider:
    providers: list[Provider] = getattr(config.data_sources, group)
    enabled = sorted((provider for provider in providers if provider.enabled), key=lambda item: item.priority)
    if not enabled:
        raise HTTPException(status_code=503, detail=f"No {group.replace('_', ' ')} provider is enabled")
    return enabled[0]


def fetch_provider_data(provider: Provider, params: dict[str, Any], env: EnvSettings) -> dict[str, Any]:
    request_params = dict(params)
    if provider.name.startswith("open_meteo") and env.open_meteo_api_key:
        request_params["apikey"] = env.open_meteo_api_key

    last_error: httpx.HTTPError | None = None
    for _ in range(provider.retries + 1):
        try:
            response = httpx.get(provider.base_url, params=request_params, timeout=provider.timeout_seconds)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            last_error = exc

    raise HTTPException(
        status_code=502,
        detail=f"{provider.name} could not provide environmental data",
    ) from last_error


def get_observations(
    config: AppConfig,
    env: EnvSettings,
    kind: str,
    latitude: float,
    longitude: float,
    past_days: int = 1,
    forecast_days: int = 4,
) -> dict[str, Any]:
    provider = _provider(config, kind)
    params: dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": config.settings.app.timezone,
        "current": ",".join(provider.current_variables),
        "hourly": ",".join(provider.hourly_variables),
        "past_days": past_days,
        "forecast_days": forecast_days,
    }
    data = fetch_provider_data(provider, params, env)
    return {
        "provider": provider.name,
        "data_class": provider.data_class,
        "retrieved_at": data.get("current", {}).get("time"),
        "data": data,
    }


def simulate(config: AppConfig, values: dict[str, float]) -> dict[str, Any]:
    settings = config.simulation
    expected = set(settings.parameters)
    if set(values) != expected:
        raise HTTPException(status_code=422, detail="Provide exactly one value for every configured simulator parameter")

    for name, value in values.items():
        bounds = settings.parameters[name]
        if not math.isfinite(value) or not bounds.min <= value <= bounds.max:
            raise HTTPException(status_code=422, detail=f"{name} must be between {bounds.min:g} and {bounds.max:g}")

    source_inputs = {
        "firecracker": values["firecracker_activity"],
        "traffic": values["traffic_intensity"],
        "industrial": values["industrial_activity"],
        "construction": values["construction_activity"],
    }
    emissions = {"pm25": 0.0, "pm10": 0.0}
    for source_name, activity in source_inputs.items():
        source = settings.sources[source_name]
        fraction = activity / 100
        emissions["pm25"] += source.pm25_full_activity_ugm3 * fraction**source.response_exponent
        emissions["pm10"] += source.pm10_full_activity_ugm3 * fraction**source.response_exponent

    wind = settings.dispersion.wind
    wind_factor = min(
        wind.max_factor,
        max(wind.min_factor, (wind.reference_speed_kmh / max(values["wind_speed"], 1)) ** wind.exponent),
    )
    rain = settings.dispersion.rain_washout
    rain_factor = max(1 - rain.max_removal, 1 - values["rainfall"] * rain.per_mm)
    humidity = settings.dispersion.humidity
    humidity_factor = 1 + max(0, values["humidity"] - humidity.threshold_pct) * humidity.pm25_gain_per_pct
    temperature = settings.dispersion.temperature
    cold_penalty = min(
        temperature.max_penalty,
        max(0, temperature.cold_reference_degc - values["temperature"]) * temperature.cold_penalty_per_degc,
    )
    dispersion_factor = wind_factor * rain_factor

    pm25 = settings.background.pm25_ugm3 + emissions["pm25"] * dispersion_factor * humidity_factor * (1 + cold_penalty)
    pm10 = settings.background.pm10_ugm3 + emissions["pm10"] * dispersion_factor * (1 + cold_penalty)
    relative_band = settings.uncertainty.relative_band
    return {
        "calibration_status": settings.calibration_status,
        "assumption_label": settings.uncertainty.label,
        "pollutants": {
            "pm25": {"value": round(pm25, 1), "unit": "ug/m3", "range": [round(pm25 * (1 - relative_band), 1), round(pm25 * (1 + relative_band), 1)]},
            "pm10": {"value": round(pm10, 1), "unit": "ug/m3", "range": [round(pm10 * (1 - relative_band), 1), round(pm10 * (1 + relative_band), 1)]},
        },
        "limitations": "Illustrative scenario only; coefficients are uncalibrated and are not a forecast or measured AQI.",
    }

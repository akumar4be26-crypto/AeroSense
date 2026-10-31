"""Indian National AQI (CPCB) calculation driven by config/aqi_breakpoints.yaml."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from app.core.config import AQIConfig

# Provider variable -> CPCB pollutant key. NH3 and Pb are not supplied by the
# configured providers, so they are never invented.
PROVIDER_TO_CPCB = {
    "pm2_5": "pm25",
    "pm10": "pm10",
    "nitrogen_dioxide": "no2",
    "sulphur_dioxide": "so2",
    "carbon_monoxide": "co",
    "ozone": "o3",
}
POLLUTANT_COLUMNS = list(PROVIDER_TO_CPCB.values())

WINDOW_HOURS = {"24h": 24, "8h": 8}
# CPCB requires at least 16 valid hourly values for a 24 h average (6 of 8 for 8 h averages).
MIN_VALID_HOURS = {"24h": 16, "8h": 6}


def _finite(value: Any) -> bool:
    return value is not None and isinstance(value, (int, float, np.floating)) and math.isfinite(value)


def sub_index(cfg: AQIConfig, pollutant: str, concentration: float | None) -> float | None:
    """Piecewise-linear CPCB sub-index for one averaged concentration."""
    if not _finite(concentration) or concentration < 0:
        return None
    c_hi = cfg.pollutants[pollutant].c_hi
    last = len(c_hi) - 1
    for i, upper in enumerate(c_hi):
        lower = c_hi[i - 1] if i > 0 else 0.0
        if upper is None:
            # Open-ended top band: extend the previous band's width (see open_ended_policy).
            upper = lower + (c_hi[i - 1] - c_hi[i - 2])
        if concentration <= upper or i == last:
            index_lo, index_hi = cfg.index_bands[i]
            value = (index_hi - index_lo) / (upper - lower) * (concentration - lower) + index_lo
            return min(float(value), float(cfg.index_bands[-1][1]))
    return None  # unreachable: the loop always returns on the last band


def category_for(cfg: AQIConfig, aqi: float | None) -> str | None:
    if aqi is None:
        return None
    rounded = round(aqi)
    for category in cfg.categories:
        if category.min <= rounded <= category.max:
            return category.name
    return cfg.categories[-1].name if rounded > cfg.categories[-1].max else None


def _to_cpcb_unit(cfg: AQIConfig, pollutant: str, value: float) -> float:
    # Providers report CO in ug/m3; CPCB uses mg/m3.
    return value * cfg.unit_conversions["co_ugm3_to_mgm3"] if pollutant == "co" else value


def compute_aqi(cfg: AQIConfig, averaged: dict[str, float | None]) -> dict[str, Any]:
    """Overall AQI from already-averaged concentrations in CPCB units (CO in mg/m3)."""
    sub_indices = {
        pollutant: sub_index(cfg, pollutant, concentration)
        for pollutant, concentration in averaged.items()
        if pollutant in cfg.pollutants
    }
    valid = {k: v for k, v in sub_indices.items() if v is not None}
    meets_count = len(valid) >= cfg.validity.min_pollutants
    meets_required = any(p in valid for p in cfg.validity.required_one_of)
    if not (meets_count and meets_required):
        return {
            "aqi": None,
            "category": None,
            "dominant_pollutant": None,
            "sub_indices": {k: None if v is None else round(v) for k, v in sub_indices.items()},
            "reason": (
                f"At least {cfg.validity.min_pollutants} pollutants including one of "
                f"{', '.join(cfg.validity.required_one_of)} are required."
            ),
        }
    dominant = max(valid, key=lambda k: valid[k])
    aqi = round(valid[dominant])
    return {
        "aqi": aqi,
        "category": category_for(cfg, aqi),
        "dominant_pollutant": dominant,
        "sub_indices": {k: None if v is None else round(v) for k, v in sub_indices.items()},
        "reason": None,
    }


def trailing_average(values: list[float | None], window: int, minimum: int) -> float | None:
    recent = [v for v in values[-window:] if _finite(v)]
    return float(np.mean(recent)) if len(recent) >= minimum else None


def aqi_from_hourly(cfg: AQIConfig, hourly: dict[str, list[float | None]]) -> dict[str, Any]:
    """AQI for the most recent hour in `hourly` (keys are CPCB pollutant names, oldest first)."""
    averaged: dict[str, float | None] = {}
    details: dict[str, Any] = {}
    for pollutant, series in hourly.items():
        if pollutant not in cfg.pollutants:
            continue
        spec = cfg.pollutants[pollutant]
        mean = trailing_average(series, WINDOW_HOURS[spec.averaging], MIN_VALID_HOURS[spec.averaging])
        converted = None if mean is None else _to_cpcb_unit(cfg, pollutant, mean)
        averaged[pollutant] = converted
        details[pollutant] = {
            "label": spec.label,
            "averaging": spec.averaging,
            "concentration": None if converted is None else round(converted, 2),
            "unit": spec.unit,
        }
    result = compute_aqi(cfg, averaged)
    for pollutant, detail in details.items():
        detail["sub_index"] = result["sub_indices"].get(pollutant)
    result["pollutants"] = details
    return result


def aqi_series(cfg: AQIConfig, frame: pd.DataFrame) -> pd.Series:
    """Hourly AQI for every row of a time-ordered frame with CPCB pollutant columns."""
    sub_columns: dict[str, pd.Series] = {}
    for pollutant in POLLUTANT_COLUMNS:
        if pollutant not in frame or pollutant not in cfg.pollutants:
            continue
        averaging = cfg.pollutants[pollutant].averaging
        mean = frame[pollutant].rolling(
            WINDOW_HOURS[averaging], min_periods=MIN_VALID_HOURS[averaging]
        ).mean()
        sub_columns[pollutant] = mean.map(
            lambda c, p=pollutant: np.nan
            if pd.isna(c)
            else (sub_index(cfg, p, _to_cpcb_unit(cfg, p, float(c))) or np.nan)
        )
    subs = pd.DataFrame(sub_columns, index=frame.index)
    valid_count = subs.notna().sum(axis=1)
    has_required = subs[[p for p in cfg.validity.required_one_of if p in subs]].notna().any(axis=1)
    aqi = subs.max(axis=1).round()
    return aqi.where((valid_count >= cfg.validity.min_pollutants) & has_required)

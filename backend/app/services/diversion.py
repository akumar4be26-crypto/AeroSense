"""Traffic-diversion advisories from forecast stagnation and modelled particulates.

Decision support only. There is no traffic-count, emission-inventory or road-network
data in this project, so this module never names routes or claims street-level hotspots;
it flags time windows and district-scale zones where dispersion is poor and
modelled particulates are high.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import AppConfig, DiversionConfig
from app.core.env import EnvSettings
from app.ml.aqi import PROVIDER_TO_CPCB, aqi_from_hourly
from app.services.environmental import _provider, fetch_provider_data

KM_PER_DEG = 111.0
TIER_RANK = {"clear": 0, "watch": 1, "divert": 2}


def build_grid(cfg: DiversionConfig, latitude: float, longitude: float) -> list[dict[str, Any]]:
    half = cfg.grid.size // 2
    cells = []
    for row in range(half, -half - 1, -1):  # north first
        for col in range(-half, half + 1):
            ns = "N" if row > 0 else "S" if row < 0 else ""
            ew = "E" if col > 0 else "W" if col < 0 else ""
            km = round(max(abs(row), abs(col)) * cfg.grid.spacing_deg * KM_PER_DEG)
            cells.append({
                "id": f"r{row}c{col}",
                "label": "Centre" if not (ns or ew) else f"{ns}{ew} · ~{km} km",
                "row": half - row,
                "col": col + half,
                "latitude": round(latitude + row * cfg.grid.spacing_deg, 4),
                "longitude": round(longitude + col * cfg.grid.spacing_deg, 4),
            })
    return cells


def classify(cfg: DiversionConfig, wind: float | None, blh: float | None, pm25: float | None, pm10: float | None) -> dict[str, Any]:
    """Tier for one cell-hour. Missing inputs never count as evidence of risk or of safety."""
    if wind is None or blh is None or (pm25 is None and pm10 is None):
        return {"tier": "unknown", "ventilation_m2s": None, "stagnant": None, "score": None, "reasons": ["Incomplete provider data"]}
    ventilation = wind * blh
    stagnant = wind < cfg.stagnation.low_wind_ms or ventilation <= cfg.stagnation.poor_ventilation_m2s
    sev, ele = cfg.pollution.severe, cfg.pollution.elevated
    severe = (pm25 is not None and pm25 >= sev.pm25) or (pm10 is not None and pm10 >= sev.pm10)
    elevated = (pm25 is not None and pm25 >= ele.pm25) or (pm10 is not None and pm10 >= ele.pm10)
    if stagnant and severe:
        tier = "divert"
    elif stagnant and elevated:
        tier = "watch"
    elif severe:
        tier = "watch"
    else:
        tier = "clear"
    reasons = []
    if wind < cfg.stagnation.low_wind_ms:
        reasons.append(f"Calm wind ({wind:.1f} m/s)")
    if ventilation <= cfg.stagnation.poor_ventilation_m2s:
        reasons.append(f"Poor ventilation index ({ventilation:.0f} m²/s)")
    if pm25 is not None and pm25 >= ele.pm25:
        reasons.append(f"PM2.5 {pm25:.0f} µg/m³")
    if pm10 is not None and pm10 >= ele.pm10:
        reasons.append(f"PM10 {pm10:.0f} µg/m³")
    # Ranking score: particulate load relative to its severe threshold, amplified by poor dispersion.
    load = max(
        (pm25 / sev.pm25) if pm25 is not None else 0.0,
        (pm10 / sev.pm10) if pm10 is not None else 0.0,
    )
    dispersion = cfg.stagnation.poor_ventilation_m2s / max(ventilation, cfg.stagnation.poor_ventilation_m2s / 10)
    return {
        "tier": tier,
        "ventilation_m2s": round(ventilation),
        "stagnant": stagnant,
        "score": round(load * dispersion, 2),
        "reasons": reasons,
    }


def _cell_hours(cfg: DiversionConfig, weather: dict[str, Any], air: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    w, a = weather["hourly"], air["hourly"]
    air_index = {t: i for i, t in enumerate(a["time"])}
    out = []
    for i, t in enumerate(w["time"]):
        if datetime.fromisoformat(t) < now:
            continue
        j = air_index.get(t)
        if j is None:
            continue
        reading = {
            "wind_ms": w["wind_speed_10m"][i],
            "boundary_layer_m": w["boundary_layer_height"][i],
            "pm25": a["pm2_5"][j],
            "pm10": a["pm10"][j],
            "no2": a.get("nitrogen_dioxide", [None] * len(a["time"]))[j],
            "co": a.get("carbon_monoxide", [None] * len(a["time"]))[j],
        }
        out.append({"time": t, **reading, **classify(cfg, reading["wind_ms"], reading["boundary_layer_m"], reading["pm25"], reading["pm10"])})
        if len(out) >= cfg.horizon_hours:
            break
    return out


def zone_aqi(config: AppConfig, air: dict[str, Any], time: str) -> dict[str, Any]:
    """CPCB-method AQI for one zone at `time`, using trailing averages from the modelled series."""
    hourly = air["hourly"]
    try:
        end = hourly["time"].index(time) + 1
    except ValueError:
        end = 0
    series = {cpcb: hourly[prov][:end] for prov, cpcb in PROVIDER_TO_CPCB.items() if prov in hourly}
    result = aqi_from_hourly(config.aqi, series)
    return {
        "aqi": result["aqi"],
        "aqi_category": result["category"],
        "dominant_pollutant": result["dominant_pollutant"],
        "sub_indices": result["sub_indices"],
        "pollutants": {k: v["concentration"] for k, v in result["pollutants"].items()},
    }


def _zones_at(config: AppConfig, cells, per_cell, air_by_cell, idx: int, labels) -> list[dict[str, Any]]:
    zones = []
    for cell in cells:
        h = per_cell[cell["id"]][idx]
        zones.append({
            "id": cell["id"], "label": cell["label"], "row": cell["row"], "col": cell["col"],
            "latitude": cell["latitude"], "longitude": cell["longitude"],
            "tier": h["tier"], "tier_label": labels.get(h["tier"], "Unavailable"), "score": h["score"],
            "wind_ms": h["wind_ms"], "boundary_layer_m": h["boundary_layer_m"], "ventilation_m2s": h["ventilation_m2s"],
            "pm25": h["pm25"], "pm10": h["pm10"], "no2": h["no2"], "co": h["co"], "reasons": h["reasons"],
            **zone_aqi(config, air_by_cell[cell["id"]], h["time"]),
        })
    return zones


def assess(config: AppConfig, cells: list[dict[str, Any]], weather: list[dict[str, Any]], air: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    cfg = config.diversion
    per_cell = {c["id"]: _cell_hours(cfg, w, a, now) for c, w, a in zip(cells, weather, air, strict=True)}
    air_by_cell = {c["id"]: a for c, a in zip(cells, air, strict=True)}
    centre_id = next(c["id"] for c in cells if c["label"] == "Centre")
    centre = per_cell[centre_id]
    labels = {"clear": cfg.tiers.clear_label, "watch": cfg.tiers.watch_label, "divert": cfg.tiers.divert_label}

    # An area-wide tier per hour: the worst tier in any cell, so a pocket anywhere in the area is not averaged away.
    hours = []
    for idx, hour in enumerate(centre):
        cell_hours = [per_cell[c["id"]][idx] for c in cells if idx < len(per_cell[c["id"]])]
        known = [h["tier"] for h in cell_hours if h["tier"] != "unknown"]
        worst = max(known, key=lambda t: TIER_RANK[t]) if known else "unknown"
        hours.append({"time": hour["time"], "tier": worst, "label": labels.get(worst, "Unavailable")})

    # One window per run of consecutive hours at the same tier (watch or divert).
    windows = []
    start = 0
    for idx in range(1, len(hours) + 1):
        if idx < len(hours) and hours[idx]["tier"] == hours[start]["tier"]:
            continue
        if TIER_RANK.get(hours[start]["tier"], 0) >= 1 and (idx - start >= cfg.minimum_window_hours or hours[start]["tier"] == "divert"):
            windows.append(_window(config, cells, per_cell, air_by_cell, hours, start, idx, labels))
        start = idx

    return {
        "as_of": now.isoformat(timespec="minutes"),
        "calibration_status": cfg.calibration_status,
        "current": hours[0] if hours else None,
        "current_zones": _zones_at(config, cells, per_cell, air_by_cell, 0, labels) if hours else [],
        "hours": hours,
        "windows": windows,
        "grid": {"size": cfg.grid.size, "spacing_deg": cfg.grid.spacing_deg, "cells": [{k: c[k] for k in ("id", "label", "row", "col", "latitude", "longitude")} for c in cells]},
        "thresholds": {
            "low_wind_ms": cfg.stagnation.low_wind_ms,
            "poor_ventilation_m2s": cfg.stagnation.poor_ventilation_m2s,
            "elevated": cfg.pollution.elevated.model_dump(),
            "severe": cfg.pollution.severe.model_dump(),
        },
    }


def _window(config: AppConfig, cells: list[dict[str, Any]], per_cell: dict[str, list[dict[str, Any]]], air_by_cell: dict[str, Any], hours: list[dict[str, Any]], start: int, end: int, labels: dict[str, str]) -> dict[str, Any]:
    cfg = config.diversion
    span = hours[start:end]
    tier = max((h["tier"] for h in span), key=lambda t: TIER_RANK.get(t, 0))
    # Peak hour = the worst hour by the highest cell score.
    def hour_score(idx: int) -> float:
        return max((per_cell[c["id"]][idx]["score"] or 0.0) for c in cells)

    peak_idx = max(range(start, end), key=hour_score)
    zones = _zones_at(config, cells, per_cell, air_by_cell, peak_idx, labels)
    ranked = sorted(zones, key=lambda z: z["score"] if z["score"] is not None else -1, reverse=True)
    spread = [z["pm25"] for z in zones if z["pm25"] is not None]
    uniform_pollution = bool(spread) and (max(spread) - min(spread)) < 1.0
    return {
        "start": hours[start]["time"],
        "end": hours[end - 1]["time"],
        "hours": end - start,
        "tier": tier,
        "label": labels[tier],
        "peak_time": hours[peak_idx]["time"],
        "zones": zones,
        "ranked_zones": [z["id"] for z in ranked],
        "uniform_pollution": uniform_pollution,
        "suggested_action": (
            "Consider diverting heavy commercial vehicles away from the listed zones during this window; confirm against local conditions."
            if tier == "divert"
            else "Prepare diversion plans and monitor; conditions may deteriorate."
        ),
    }


def _as_list(payload: Any) -> list[dict[str, Any]]:
    return payload if isinstance(payload, list) else [payload]


def get_diversion(config: AppConfig, env: EnvSettings, latitude: float, longitude: float, now: datetime | None = None) -> dict[str, Any]:
    cfg = config.diversion
    cells = build_grid(cfg, latitude, longitude)
    tz = ZoneInfo(config.settings.app.timezone)
    now = (now or datetime.now(tz)).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    days = cfg.horizon_hours // 24 + 2
    shared = {
        "latitude": ",".join(str(c["latitude"]) for c in cells),
        "longitude": ",".join(str(c["longitude"]) for c in cells),
        "timezone": config.settings.app.timezone,
        "forecast_days": days,
    }
    weather_provider = _provider(config, "weather")
    air_provider = _provider(config, "air_quality")
    weather = _as_list(fetch_provider_data(
        weather_provider,
        {**shared, "hourly": ",".join(cfg.provider_variables["weather"]), "wind_speed_unit": "ms"},
        env,
    ))
    air = _as_list(fetch_provider_data(air_provider, {**shared, "past_days": 2, "hourly": ",".join(cfg.provider_variables["air_quality"])}, env))
    result = assess(config, cells, weather, air, now)
    result.update({
        "weather_provider": weather_provider.name,
        "air_quality_provider": air_provider.name,
        "air_quality_data_class": air_provider.data_class,
        "limitations": [
            "Advisory decision support only; the authority decides whether and where to divert.",
            "Particulates are a modelled estimate at a coarse resolution, so nearby zones often share the same modelled values; this is not a street-level hotspot map.",
            "No traffic counts, emission inventory or road network are used, so no specific routes are proposed.",
            "Thresholds are unverified defaults in config/diversion_config.yaml until reviewed by the authority.",
        ],
    })
    return result

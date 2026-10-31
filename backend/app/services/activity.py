"""Safe-travel and activity windows from forecast air quality.

Decision support only. The hourly index is the maximum CPCB-breakpoint sub-index over
*hourly* modelled concentrations (it is not the official 24 h-average AQI), and the
per-profile limits in config/activity_config.yaml are unverified defaults. Heat, rain,
traffic and personal health are not considered.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import ActivityProfile, AppConfig
from app.core.env import EnvSettings
from app.ml.aqi import PROVIDER_TO_CPCB, _to_cpcb_unit, category_for, sub_index
from app.services.environmental import _provider, fetch_provider_data

STATUS_RANK = {"safe": 0, "caution": 1, "avoid": 2}


def hourly_index(config: AppConfig, hourly: dict[str, list[Any]], i: int) -> dict[str, Any]:
    subs: dict[str, float] = {}
    for provider_name, cpcb in PROVIDER_TO_CPCB.items():
        series = hourly.get(provider_name)
        if series is None or cpcb not in config.aqi.pollutants:
            continue
        value = series[i]
        if value is None:
            continue
        converted = _to_cpcb_unit(config.aqi, cpcb, value)
        idx = sub_index(config.aqi, cpcb, converted)
        if idx is not None:
            subs[cpcb] = idx
    required = config.aqi.validity.required_one_of
    if len(subs) < config.aqi.validity.min_pollutants or not any(p in subs for p in required):
        return {"index": None, "category": None, "dominant_pollutant": None}
    dominant = max(subs, key=lambda k: subs[k])
    value = round(subs[dominant])
    return {"index": value, "category": category_for(config.aqi, value), "dominant_pollutant": dominant}


def status_for(profile: ActivityProfile, index: int | None) -> str:
    if index is None:
        return "unknown"
    if index <= profile.safe_max:
        return "safe"
    return "caution" if index <= profile.caution_max else "avoid"


def assess(config: AppConfig, hourly: dict[str, list[Any]], now: datetime) -> dict[str, Any]:
    cfg = config.activity
    hours: list[dict[str, Any]] = []
    for i, t in enumerate(hourly["time"]):
        stamp = datetime.fromisoformat(t)
        if stamp < now:
            continue
        hours.append({"time": t, "hour": stamp.hour, **hourly_index(config, hourly, i)})
        if len(hours) >= cfg.horizon_hours:
            break
    waking = [h for h in hours if cfg.waking_hours.start <= h["hour"] < cfg.waking_hours.end]

    profiles: dict[str, Any] = {}
    for key, profile in cfg.profiles.items():
        strip = [{"time": h["time"], "status": status_for(profile, h["index"])} for h in hours]
        statuses = {h["time"]: s["status"] for h, s in zip(hours, strip, strict=True)}
        profiles[key] = {
            "label": profile.label,
            "effort": profile.effort,
            "safe_max": profile.safe_max,
            "caution_max": profile.caution_max,
            "hours": strip,
            "safe_hours_waking": sum(1 for h in waking if statuses[h["time"]] == "safe"),
            "best_windows": _best_windows(waking, profile, cfg.best_windows_per_profile, statuses),
        }
    return {
        "as_of": now.isoformat(timespec="minutes"),
        "calibration_status": cfg.calibration_status,
        "waking_hours": cfg.waking_hours.model_dump(),
        "hours": hours,
        "profiles": profiles,
    }


def _best_windows(waking: list[dict[str, Any]], profile: ActivityProfile, count: int, statuses: dict[str, str]) -> list[dict[str, Any]]:
    """Lowest-exposure runs of `window_hours` consecutive hours; never straddles a gap in the data."""
    n = profile.window_hours
    candidates = []
    for i in range(len(waking) - n + 1):
        chunk = waking[i : i + n]
        gap_free = all(
            (datetime.fromisoformat(chunk[j + 1]["time"]) - datetime.fromisoformat(chunk[j]["time"])).total_seconds() == 3600
            for j in range(n - 1)
        )
        values = [h["index"] for h in chunk]
        if not gap_free or any(v is None for v in values):
            continue
        worst = max(chunk, key=lambda h: h["index"])
        status = max((statuses[h["time"]] for h in chunk), key=lambda s: STATUS_RANK[s])
        candidates.append({
            "start": chunk[0]["time"],
            "end": chunk[-1]["time"],
            "mean_index": round(sum(values) / n),
            "max_index": worst["index"],
            "category": worst["category"],
            "dominant_pollutant": worst["dominant_pollutant"],
            "status": status,
        })
    candidates.sort(key=lambda c: (c["mean_index"], c["start"]))
    chosen: list[dict[str, Any]] = []
    for c in candidates:
        if all(c["start"] > o["end"] or c["end"] < o["start"] for o in chosen):
            chosen.append(c)
        if len(chosen) >= count:
            break
    return sorted(chosen, key=lambda c: c["start"])


def get_activity(config: AppConfig, env: EnvSettings, latitude: float, longitude: float, now: datetime | None = None) -> dict[str, Any]:
    cfg = config.activity
    tz = ZoneInfo(config.settings.app.timezone)
    now = (now or datetime.now(tz)).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    provider = _provider(config, "air_quality")
    data = fetch_provider_data(provider, {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": config.settings.app.timezone,
        "forecast_days": cfg.horizon_hours // 24 + 2,
        "hourly": ",".join(cfg.provider_variables["air_quality"]),
    }, env)
    result = assess(config, data["hourly"], now)
    result.update({
        "provider": provider.name,
        "data_class": provider.data_class,
        "limitations": [
            "Advisory only; not medical advice. People with heart or lung conditions, children and older adults should be more cautious.",
            "The hourly index applies CPCB breakpoints to single-hour modelled concentrations; it is not the official 24-hour-average AQI and is not a station reading.",
            "Per-profile limits are unverified defaults in config/activity_config.yaml.",
            "Heat, humidity, rain, traffic and route-level pollution are not considered.",
            "When no hour is rated safe, the listed windows are only the relatively least-polluted hours.",
        ],
    })
    return result

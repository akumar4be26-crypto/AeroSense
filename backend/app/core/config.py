"""Typed loading and startup validation of the YAML configuration files.

All tunable parameters live in config/*.yaml. This module parses them into
strict Pydantic models so a typo or an impossible value fails fast at startup
instead of producing silently wrong forecasts.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ConfigError(RuntimeError):
    """Raised when configuration cannot be loaded or fails validation."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- settings.yaml
class AppInfo(_Strict):
    name: str
    full_name: str
    tagline: str
    version: str
    timezone: str


class DefaultLocation(_Strict):
    city: str
    state: str
    country: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class ForecastSettings(_Strict):
    durations_hours: list[int]
    interval_hours: int = Field(ge=1)

    @model_validator(mode="after")
    def _check(self) -> "ForecastSettings":
        d = self.durations_hours
        if not d or any(x <= 0 for x in d) or d != sorted(set(d)):
            raise ValueError("durations_hours must be a non-empty, strictly ascending list of positive integers")
        return self


class GPSSettings(_Strict):
    enabled: bool
    high_accuracy: bool
    update_interval_ms: int = Field(gt=0)
    timeout_ms: int = Field(gt=0)
    maximum_age_ms: int = Field(ge=0)
    persist_history_default: bool = False


class RefreshSettings(_Strict):
    api_refresh_interval_seconds: int = Field(gt=0)
    cache_ttl_seconds: int = Field(ge=0)
    geocode_cache_ttl_seconds: int = Field(ge=0)


class DataModeSettings(_Strict):
    default: Literal["live", "historical", "demonstration"]
    # Literal[False]: enabling silent fallback to synthetic data is rejected.
    allow_silent_fallback: Literal[False] = False


class MapSettings(_Strict):
    default_zoom: int = Field(ge=1, le=19)
    search_radii_km: list[float]
    default_radius_km: float

    @model_validator(mode="after")
    def _check(self) -> "MapSettings":
        if not self.search_radii_km or any(r <= 0 for r in self.search_radii_km):
            raise ValueError("search_radii_km must contain positive values")
        if self.default_radius_km not in self.search_radii_km:
            raise ValueError("default_radius_km must be one of search_radii_km")
        return self


class RateLimitSettings(_Strict):
    requests_per_minute: int = Field(gt=0)


class Settings(_Strict):
    app: AppInfo
    default_location: DefaultLocation
    forecast: ForecastSettings
    gps: GPSSettings
    refresh: RefreshSettings
    data_mode: DataModeSettings
    map: MapSettings
    rate_limit: RateLimitSettings


# --------------------------------------------------------------------------- model_config.yaml
class SplitConfig(_Strict):
    chronological: Literal[True]
    train_fraction: float = Field(gt=0, lt=1)


class ValidationConfig(_Strict):
    scheme: Literal["time_series_split"]
    cv_folds: int = Field(ge=2)


class CandidateModel(_Strict):
    enabled: bool
    params: dict[str, Any] = {}


class FeatureConfig(_Strict):
    historical_pollution: list[str]
    weather: list[str]
    activity_indices: list[str]
    temporal: list[str]
    lag_hours: list[int]
    rolling_windows_hours: list[int]


class ModelConfig(_Strict):
    model_version: str
    random_seed: int
    targets: list[str]
    horizons_hours: list[int]
    split: SplitConfig
    validation: ValidationConfig
    metrics: list[str]
    selection_metric: str
    min_training_rows: int = Field(gt=0)
    artifacts_dir: str
    candidates: dict[str, CandidateModel]
    features: FeatureConfig

    @model_validator(mode="after")
    def _check(self) -> "ModelConfig":
        if self.selection_metric not in self.metrics:
            raise ValueError("selection_metric must be listed in metrics")
        if "persistence" not in self.candidates:
            raise ValueError("a 'persistence' baseline candidate is required")
        if not any(c.enabled for c in self.candidates.values()):
            raise ValueError("at least one candidate model must be enabled")
        return self


# --------------------------------------------------------------------------- simulation_config.yaml
REQUIRED_SIM_PARAMETERS = {
    "firecracker_activity", "traffic_intensity", "industrial_activity", "construction_activity",
    "wind_speed", "humidity", "rainfall", "temperature",
}


class ParamRange(_Strict):
    min: float
    default: float
    max: float
    unit: str

    @model_validator(mode="after")
    def _check(self) -> "ParamRange":
        if not (self.min <= self.default <= self.max):
            raise ValueError(f"require min <= default <= max, got {self.min}, {self.default}, {self.max}")
        return self


class SourceFactor(_Strict):
    pm25_full_activity_ugm3: float = Field(ge=0)
    pm10_full_activity_ugm3: float = Field(ge=0)
    response_exponent: float = Field(gt=0)


class Background(_Strict):
    pm25_ugm3: float = Field(ge=0)
    pm10_ugm3: float = Field(ge=0)


class WindDispersion(_Strict):
    reference_speed_kmh: float = Field(gt=0)
    exponent: float = Field(ge=0)
    min_factor: float = Field(gt=0)
    max_factor: float = Field(gt=0)


class RainWashout(_Strict):
    per_mm: float = Field(ge=0)
    max_removal: float = Field(ge=0, le=1)


class HumidityEffect(_Strict):
    threshold_pct: float = Field(ge=0, le=100)
    pm25_gain_per_pct: float = Field(ge=0)


class TemperatureEffect(_Strict):
    cold_reference_degc: float
    cold_penalty_per_degc: float = Field(ge=0)
    max_penalty: float = Field(ge=0, le=1)


class Dispersion(_Strict):
    wind: WindDispersion
    rain_washout: RainWashout
    humidity: HumidityEffect
    temperature: TemperatureEffect


class Uncertainty(_Strict):
    relative_band: float = Field(ge=0, le=1)
    label: str


class SimulationConfig(_Strict):
    calibration_status: Literal["illustrative_uncalibrated", "calibrated"]
    parameters: dict[str, ParamRange]
    sources: dict[str, SourceFactor]
    background: Background
    dispersion: Dispersion
    uncertainty: Uncertainty

    @model_validator(mode="after")
    def _check(self) -> "SimulationConfig":
        missing = REQUIRED_SIM_PARAMETERS - set(self.parameters)
        if missing:
            raise ValueError(f"missing simulator parameters: {sorted(missing)}")
        return self


# --------------------------------------------------------------------------- aqi_breakpoints.yaml
REQUIRED_AQI_POLLUTANTS = {"pm25", "pm10", "no2", "so2", "co", "o3", "nh3", "pb"}


class AQICategory(_Strict):
    name: str
    min: int
    max: int


class AQIValidity(_Strict):
    min_pollutants: int = Field(ge=1)
    required_one_of: list[str]


class AQIPollutant(_Strict):
    label: str
    unit: str
    averaging: str
    c_hi: list[float | None]

    @model_validator(mode="after")
    def _check(self) -> "AQIPollutant":
        if len(self.c_hi) != 6:
            raise ValueError("each pollutant needs 6 upper breakpoints (one per AQI band)")
        if self.c_hi[-1] is not None:
            raise ValueError("the last band must be open-ended (null)")
        finite = [v for v in self.c_hi[:-1] if v is not None]
        if len(finite) != 5 or any(b <= a for a, b in zip(finite, finite[1:])) or finite[0] <= 0:
            raise ValueError("upper breakpoints must be positive and strictly increasing")
        return self


class AQIConfig(_Strict):
    open_ended_policy: str
    categories: list[AQICategory]
    validity: AQIValidity
    index_bands: list[list[int]]
    pollutants: dict[str, AQIPollutant]
    unit_conversions: dict[str, float]

    @model_validator(mode="after")
    def _check(self) -> "AQIConfig":
        if len(self.categories) != 6:
            raise ValueError("Indian AQI defines exactly 6 categories")
        expected = [(0, 50), (51, 100), (101, 200), (201, 300), (301, 400), (401, 500)]
        if [(c.min, c.max) for c in self.categories] != expected:
            raise ValueError(f"category ranges must equal {expected}")
        if [tuple(b) for b in self.index_bands] != expected:
            raise ValueError("index_bands must match the CPCB category ranges")
        missing = REQUIRED_AQI_POLLUTANTS - set(self.pollutants)
        if missing:
            raise ValueError(f"missing pollutants: {sorted(missing)}")
        for p in self.validity.required_one_of:
            if p not in self.pollutants:
                raise ValueError(f"validity.required_one_of references unknown pollutant '{p}'")
        return self


# --------------------------------------------------------------------------- data_sources.yaml
class Provider(_Strict):
    name: str
    enabled: bool
    priority: int = Field(ge=1)
    base_url: str
    timeout_seconds: float = Field(gt=0)
    retries: int = Field(ge=0)
    refresh_seconds: int | None = None
    data_class: str | None = None
    current_variables: list[str] = []
    hourly_variables: list[str] = []
    min_interval_seconds: float | None = None
    cache_ttl_seconds: int | None = None
    cache_key_decimals: int | None = None


class DataSourcesConfig(_Strict):
    data_classes: list[str]
    weather: list[Provider]
    air_quality: list[Provider]
    reverse_geocoding: list[Provider]
    ground_stations: list[dict[str, Any]] = []

    @model_validator(mode="after")
    def _check(self) -> "DataSourcesConfig":
        for kind in ("weather", "air_quality", "reverse_geocoding"):
            providers: list[Provider] = getattr(self, kind)
            priorities = [p.priority for p in providers if p.enabled]
            if len(priorities) != len(set(priorities)):
                raise ValueError(f"{kind}: enabled providers must have unique priorities")
            for p in providers:
                if not p.base_url.startswith("https://"):
                    raise ValueError(f"{kind}/{p.name}: base_url must use HTTPS")
                if p.data_class and p.data_class not in self.data_classes:
                    raise ValueError(f"{kind}/{p.name}: unknown data_class '{p.data_class}'")
        return self


# --------------------------------------------------------------------------- diversion_config.yaml
class DiversionGrid(_Strict):
    size: int = Field(ge=1, le=7)
    spacing_deg: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def _odd(self) -> "DiversionGrid":
        if self.size % 2 == 0:
            raise ValueError("grid.size must be odd so the selected location is the centre cell")
        return self


class DiversionStagnation(_Strict):
    low_wind_ms: float = Field(gt=0)
    poor_ventilation_m2s: float = Field(gt=0)


class PollutantThresholds(_Strict):
    pm25: float = Field(gt=0)
    pm10: float = Field(gt=0)


class DiversionPollution(_Strict):
    elevated: PollutantThresholds
    severe: PollutantThresholds


class DiversionTiers(_Strict):
    watch_label: str
    divert_label: str
    clear_label: str


class DiversionConfig(_Strict):
    calibration_status: str
    grid: DiversionGrid
    horizon_hours: int = Field(ge=1, le=96)
    provider_variables: dict[str, list[str]]
    stagnation: DiversionStagnation
    pollution: DiversionPollution
    tiers: DiversionTiers
    minimum_window_hours: int = Field(ge=1)


class ActivityProfile(_Strict):
    label: str
    effort: str
    safe_max: float = Field(gt=0)
    caution_max: float = Field(gt=0)
    window_hours: int = Field(ge=1, le=6)


class WakingHours(_Strict):
    start: int = Field(ge=0, le=23)
    end: int = Field(ge=1, le=24)


class ActivityConfig(_Strict):
    calibration_status: str
    horizon_hours: int = Field(ge=1, le=96)
    waking_hours: WakingHours
    provider_variables: dict[str, list[str]]
    profiles: dict[str, ActivityProfile]
    best_windows_per_profile: int = Field(ge=1, le=10)


# --------------------------------------------------------------------------- aggregate + loader
class AppConfig(_Strict):
    settings: Settings
    model: ModelConfig
    simulation: SimulationConfig
    aqi: AQIConfig
    data_sources: DataSourcesConfig
    diversion: DiversionConfig
    activity: ActivityConfig


_FILES = {
    "settings": ("settings.yaml", Settings),
    "model": ("model_config.yaml", ModelConfig),
    "simulation": ("simulation_config.yaml", SimulationConfig),
    "aqi": ("aqi_breakpoints.yaml", AQIConfig),
    "data_sources": ("data_sources.yaml", DataSourcesConfig),
    "diversion": ("diversion_config.yaml", DiversionConfig),
    "activity": ("activity_config.yaml", ActivityConfig),
}


def default_config_dir() -> Path:
    env = os.environ.get("AERIS_CONFIG_DIR")
    if env:
        return Path(env)
    # backend/app/core/config.py -> repo root is three parents above "app"
    return Path(__file__).resolve().parents[3] / "config"


def load_config(config_dir: Path | str | None = None) -> AppConfig:
    """Load and validate every config file. Raises ConfigError with all problems."""
    base = Path(config_dir) if config_dir else default_config_dir()
    loaded: dict[str, Any] = {}
    problems: list[str] = []
    for key, (filename, model) in _FILES.items():
        path = base / filename
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            problems.append(f"{filename}: file not found in {base}")
            continue
        except yaml.YAMLError as exc:
            problems.append(f"{filename}: invalid YAML ({exc})")
            continue
        try:
            loaded[key] = model.model_validate(raw)
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(p) for p in err["loc"])
                problems.append(f"{filename}: {loc}: {err['msg']}")
    if problems:
        raise ConfigError("Configuration invalid:\n  - " + "\n  - ".join(problems))
    return AppConfig(**loaded)


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return load_config()

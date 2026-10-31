from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel


class DataClass(str, Enum):
    """Every dataset must carry one of these. Modelled estimates are never sensors."""

    LIVE_OBSERVATION = "LIVE_OBSERVATION"
    GROUND_STATION_OBSERVATION = "GROUND_STATION_OBSERVATION"
    MODELLED_ESTIMATE = "MODELLED_ESTIMATE"
    WEATHER_FORECAST = "WEATHER_FORECAST"
    AIR_QUALITY_FORECAST = "AIR_QUALITY_FORECAST"
    SYNTHETIC_DEMONSTRATION_DATA = "SYNTHETIC_DEMONSTRATION_DATA"


class DataMode(str, Enum):
    LIVE = "live"
    HISTORICAL = "historical"
    DEMONSTRATION = "demonstration"


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    app: str
    version: str
    environment: str
    time: datetime
    database: Literal["ok", "unavailable"]
    config_valid: bool

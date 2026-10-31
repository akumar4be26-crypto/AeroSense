"""SQLAlchemy entities. Works on PostgreSQL (production) and SQLite (local dev).

Privacy: these tables store places and measurements, not a per-user trail of
precise GPS fixes. The `locations` table holds named localities; precise device
coordinates are only used transiently for a request unless the user opts in.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (Index("ix_locations_lat_lon", "latitude", "longitude"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city: Mapped[str] = mapped_column(String(120), index=True)
    state: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(120))
    neighbourhood: Mapped[str | None] = mapped_column(String(160))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    geojson_boundary: Mapped[dict | None] = mapped_column(JSON)


class AirQualityObservation(Base):
    __tablename__ = "air_quality_observations"
    __table_args__ = (
        UniqueConstraint("location_id", "timestamp", "data_source", name="uq_aq_loc_ts_source"),
        Index("ix_aq_location_timestamp", "location_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    aqi: Mapped[float | None] = mapped_column(Float)
    pm25: Mapped[float | None] = mapped_column(Float)
    pm10: Mapped[float | None] = mapped_column(Float)
    no2: Mapped[float | None] = mapped_column(Float)
    so2: Mapped[float | None] = mapped_column(Float)
    co: Mapped[float | None] = mapped_column(Float)
    o3: Mapped[float | None] = mapped_column(Float)
    data_source: Mapped[str] = mapped_column(String(80))
    # One of app.schemas.common.DataClass
    data_type: Mapped[str] = mapped_column(String(40))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)

    location: Mapped[Location] = relationship()


class WeatherObservation(Base):
    __tablename__ = "weather_observations"
    __table_args__ = (
        UniqueConstraint("location_id", "timestamp", name="uq_weather_loc_ts"),
        Index("ix_weather_location_timestamp", "location_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    temperature: Mapped[float | None] = mapped_column(Float)
    humidity: Mapped[float | None] = mapped_column(Float)
    wind_speed: Mapped[float | None] = mapped_column(Float)
    wind_direction: Mapped[float | None] = mapped_column(Float)
    pressure: Mapped[float | None] = mapped_column(Float)
    rainfall: Mapped[float | None] = mapped_column(Float)

    location: Mapped[Location] = relationship()


class TrafficObservation(Base):
    __tablename__ = "traffic_observations"
    __table_args__ = (Index("ix_traffic_location_timestamp", "location_id", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    traffic_intensity: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(80))

    location: Mapped[Location] = relationship()


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        Index("ix_pred_location_target", "location_id", "target_timestamp"),
        Index("ix_pred_model_version", "model_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"))
    prediction_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    target_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    predicted_aqi: Mapped[float | None] = mapped_column(Float)
    predicted_pm25: Mapped[float | None] = mapped_column(Float)
    predicted_pm10: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(40))
    confidence_interval: Mapped[dict | None] = mapped_column(JSON)
    data_source: Mapped[str] = mapped_column(String(80))

    location: Mapped[Location] = relationship()


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), index=True)
    scenario_name: Mapped[str] = mapped_column(String(160))
    parameters_json: Mapped[dict] = mapped_column(JSON)
    predicted_results_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CommunityReport(Base):
    """Unverified citizen observation. Never treated as a verified measurement."""

    __tablename__ = "community_reports"
    __table_args__ = (Index("ix_reports_created", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"))
    report_type: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20))
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

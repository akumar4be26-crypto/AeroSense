"""Environment-driven secrets and deployment settings (never exposed to the frontend)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[3] / ".env", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite:///./aeris.db"
    secret_key: str = "change-me"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    open_meteo_api_key: str = ""
    geocoder_user_agent: str = "AERIS/0.1"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @model_validator(mode="after")
    def _production_guard(self) -> "EnvSettings":
        if self.is_production and self.secret_key in {"", "change-me"}:
            raise ValueError("SECRET_KEY must be set to a strong random value in production")
        return self


@lru_cache(maxsize=1)
def get_env() -> EnvSettings:
    return EnvSettings()

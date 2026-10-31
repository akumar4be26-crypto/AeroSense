import os

# Use an isolated database for tests before the app module is imported.
os.environ["DATABASE_URL"] = "sqlite:///./test_aeris.db"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # runs lifespan: config validation + table creation
        yield c
    if os.path.exists("test_aeris.db"):
        os.remove("test_aeris.db")


def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["app"] == "AERIS"


def test_public_config_has_no_secrets_and_matches_yaml(client):
    r = client.get("/api/config/public")
    assert r.status_code == 200
    body = r.json()
    assert body["default_location"]["city"] == "Patiala"
    assert body["gps"]["timeout_ms"] == 15000
    assert body["forecast"]["durations_hours"] == [24, 48, 72]
    assert body["simulator"]["calibration_status"] == "illustrative_uncalibrated"
    flat = str(body).lower()
    for forbidden in ("secret", "password", "database_url", "api_key"):
        assert forbidden not in flat


def test_environment_endpoints_use_provider_and_validate_coordinates(client, monkeypatch):
    from app.api import routes

    calls = []

    def fake_observations(config, env, kind, latitude, longitude):
        calls.append((kind, latitude, longitude))
        return {"provider": "test-provider", "data_class": "MODELLED_ESTIMATE", "data": {}}

    monkeypatch.setattr(routes, "get_observations", fake_observations)
    response = client.get("/api/air-quality?latitude=30.35&longitude=76.37")
    assert response.status_code == 200
    assert response.json()["provider"] == "test-provider"
    assert calls == [("air_quality", 30.35, 76.37)]

    invalid = client.get("/api/weather?latitude=91&longitude=76.37")
    assert invalid.status_code == 422


def test_simulation_uses_configured_values_and_rejects_out_of_range(client):
    from app.core.config import get_config

    values = {name: parameter.default for name, parameter in get_config().simulation.parameters.items()}
    response = client.post("/api/simulation", json=values)
    assert response.status_code == 200
    result = response.json()
    assert result["calibration_status"] == "illustrative_uncalibrated"
    assert result["pollutants"]["pm25"]["value"] > 0
    assert "not a forecast" in result["limitations"]

    values["wind_speed"] = 1000
    invalid = client.post("/api/simulation", json=values)
    assert invalid.status_code == 422


def test_unknown_route_returns_structured_error(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "http_404"


def test_all_entities_create_and_relate(client):
    from datetime import datetime, timezone

    from app.database.session import _session_factory
    from app.models.entities import AirQualityObservation, Location

    with _session_factory()() as s:
        loc = Location(city="Patiala", state="Punjab", country="India", latitude=30.35, longitude=76.37)
        s.add(loc)
        s.flush()
        s.add(AirQualityObservation(
            location_id=loc.id, timestamp=datetime.now(timezone.utc), pm25=80.0,
            data_source="test", data_type="SYNTHETIC_DEMONSTRATION_DATA", is_synthetic=True,
        ))
        s.commit()
        assert s.query(AirQualityObservation).count() == 1

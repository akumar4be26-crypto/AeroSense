# AERIS — AI Environmental Risk & Intelligence System

*Predict Pollution. Understand Impact. Protect Communities.*

Neighbourhood-level air-pollution prediction, mapping, Diwali scenario simulation and health guidance,
using Indian CPCB AQI, live GPS and Open-Meteo data.

## Current functionality

- Responsive command center with an OpenStreetMap location view and explicit, session-only GPS opt-in.
- Live Open-Meteo weather and CAMS-based air-quality estimates, labelled by data class and provider.
- Hourly PM2.5/PM10 model outlook and precautionary health guidance.
- Config-driven what-if simulator. Its coefficients are illustrative and uncalibrated.
- Backend health/config endpoints and validated environmental-data/simulation APIs.

**Estimated AQI** (`GET /api/aqi`): the CPCB sub-index/max method (24 h / 8 h averages, minimum-coverage
rules) applied to Open-Meteo's CAMS-*modelled* pollutants. It is labelled as an estimate and is **not** an
official CPCB station reading.

**Local ML** (`POST /api/ml/train`, `GET /api/ml/status`, `GET /api/ml/forecast`): trains per location on
about 90 days of provider history (`config/model_config.yaml`), compares persistence and random forest
(plus XGBoost when its native runtime is available; on macOS it needs `brew install libomp`), selects by held-out
RMSE, and saves artifacts under `models/<lat>_<lon>/`. The training data is modelled, not sensor data,
so the model learns the provider's behaviour. Metrics against the persistence baseline are shown, and
where no model beats the baseline the baseline is reported as the winner. Activity and Diwali features
have no real data source and are excluded. Nothing is predicted until you train. Provider failures are shown in the UI rather than
replaced with demonstration values. See `docs/configuration.md`.

## Backend architecture, models and data

### Request and service flow

```text
React/Vite frontend
        │ HTTP (JSON)
        ▼
FastAPI routes (backend/app/api/routes.py)
        ├── config/env ── strict YAML config + environment-only secrets
        ├── services ─── provider requests, simulation, diversion, activity windows
        ├── ml ───────── CPCB AQI + local time-series training/forecasting
        └── database ─── SQLAlchemy session and schema
                 │
                 ├── Open-Meteo weather forecast API
                 ├── Open-Meteo air-quality API (CAMS model estimates)
                 └── SQLite locally / PostgreSQL when configured
```

`backend/app/main.py` validates configuration, initializes the database and mounts the API. Configuration
is parsed by strict Pydantic models in `backend/app/core/config.py`; unknown YAML fields and invalid values
fail validation at startup. Provider URLs, variables, priorities, timeouts, retries and data classifications
are in `config/data_sources.yaml`. Secrets and deployment settings come from `.env`/environment variables.
Provider errors return an explicit API error; the application does not silently substitute synthetic data.

### API surface

All endpoints are under `/api` (interactive OpenAPI docs at `/docs` when the backend is running):

| Endpoint | Method | Purpose and returned data |
|---|---:|---|
| `/health` | GET | App/config/database health. |
| `/config/public` | GET | Non-secret UI configuration, AQI categories and simulator assumptions. |
| `/weather` | GET | Current and hourly weather provider payload, with provider and data-class metadata. |
| `/air-quality` | GET | Current and hourly pollutant provider payload, with source metadata. |
| `/aqi` | GET | CPCB-method AQI, sub-indices and pollutant details derived from modelled data. |
| `/simulation` | POST | Illustrative PM2.5/PM10 scenario from activity and weather inputs. Coefficients are uncalibrated. |
| `/ml/status` | GET | Per-coordinate training artifact status and validation metrics. |
| `/ml/train` | POST | Fetches history and trains/evaluates local per-coordinate models. Returns `409` if training is busy and `422` if there is insufficient data. |
| `/ml/forecast` | GET | Forecast from the trained model; returns `409` until a model exists for that location. |
| `/diversion` | GET | 72-hour, 3×3 zone assessment from wind, boundary-layer height and modelled particulates. Advisory only; does not propose routes. |
| `/activity` | GET | 72-hour safe/caution/avoid hourly assessment and relatively clean activity windows for runner, cyclist and commuter profiles. Advisory only. |

Location endpoints take `latitude` and `longitude` query parameters. The exact pollutant fields and required
inputs are exposed in the running OpenAPI schema.

### Models and calculations

- **CPCB AQI:** `backend/app/ml/aqi.py` calculates pollutant sub-indices using the configured Indian CPCB
  breakpoints in `config/aqi_breakpoints.yaml`, then reports the maximum valid sub-index. The configured
  validity rule requires at least three pollutants including PM2.5 or PM10. PM2.5, PM10, NO₂, SO₂, CO and
  O₃ are available from the configured provider; NH₃ and Pb are not invented. The main AQI uses configured
  24-hour/8-hour averaging and minimum-coverage rules. Breakpoints are marked unverified in the config.
- **Local forecast:** `backend/app/ml/pipeline.py` builds time-ordered pollution/weather features, including
  lagged values, rolling means, temporal features and wind-direction components. It evaluates persistence,
  Random Forest (300 trees by default) and optional XGBoost (500 trees by default) for AQI, PM2.5 and PM10
  at 24/48/72-hour horizons. It uses an 80/20 chronological holdout, five-fold time-series cross-validation
  and RMSE selection; it reports MAE, RMSE, R², MAPE and skill versus persistence. Training requires at least
  720 usable hourly rows. Activity/traffic and Diwali features are excluded because no observed source is
  configured. The input history is CAMS-modelled provider data, not ground sensors.
- **Safe travel index:** applies configured CPCB pollutant sub-index breakpoints to single-hour modelled
  concentrations and takes the maximum valid sub-index. It is not the official 24-hour-average AQI.
  Runner/cyclist/commuter thresholds and waking hours are unverified defaults in `config/activity_config.yaml`.
- **Traffic diversion:** ranks cells using wind, ventilation index (wind × boundary-layer height) and
  particulate thresholds in `config/diversion_config.yaml`. It is district-scale advisory output, not a
  street-level hotspot map; the app has no traffic counts, emission inventory or road graph.
- **Scenario simulator:** computes illustrative pollutant contributions and weather adjustments from
  `config/simulation_config.yaml`. Its coefficients and uncertainty band are explicitly uncalibrated and
  must not be interpreted as measured AQI or a validated forecast.

### Datasets and generated artifacts

There are currently **no checked-in raw, sample or processed datasets**. The directories under `datasets/`
contain only `.gitkeep` placeholders. Runtime weather comes from Open-Meteo's weather forecast API;
runtime air-quality values come from its CAMS-based air-quality API and are classified as
`MODELLED_ESTIMATE`, not ground-station observations. No station feed or trusted traffic/emissions dataset
is configured (`ground_stations` is empty).

Training fetches up to 92 days of hourly provider history at request time, joins pollution and weather rows,
and creates its training frame in memory. Per-location `bundle.joblib` and `metadata.json` files are generated
under `models/<lat>_<lon>/` after training. They are local artifacts, ignored by Git, and are not included
in the repository; train again in the target environment to create them. Metadata records training period,
row counts, selected candidates, metrics, unavailable features and the modelled-data caveat.

### Database schema and persistence

The SQLAlchemy entities in `backend/app/models/entities.py` define users, locations, air-quality/weather/
traffic observations, predictions, scenarios and unverified community reports. Local development defaults
to SQLite; PostgreSQL can be selected with `DATABASE_URL`. Local startup creates the schema, while the
Docker configuration uses PostgreSQL. **The current environmental API and model pipeline do not write
provider history, predictions, scenarios or GPS trails into these tables**: requests fetch provider data
directly, and the only feature-generated persistence is the per-location ML artifact directory. The schema
is therefore broader than the active ingestion/persistence features. GPS coordinates are used for requests;
the app does not store a user's location history by default.

### Key backend files

- `backend/app/api/routes.py` — HTTP endpoints and validation.
- `backend/app/services/environmental.py` — provider selection/fetch, response metadata and simulator.
- `backend/app/services/diversion.py`, `activity.py` — zone and activity-window assessments.
- `backend/app/ml/aqi.py`, `pipeline.py` — AQI calculation and local ML pipeline.
- `backend/app/core/config.py`, `env.py` — validated YAML config and environment settings.
- `backend/app/models/entities.py`, `database/session.py` — ORM schema and database sessions.
- `backend/tests/` — API, config, AQI/ML, diversion and activity tests.

## Run locally

```bash
cp .env.example .env

# Backend (from the repository root)
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
python -m pytest
python -m uvicorn app.main:app --reload # http://127.0.0.1:8000/docs

# Frontend (new terminal)
cd frontend
npm install
npm test
npm run dev                            # http://localhost:5173
```

Docker: `docker compose up --build` starts PostgreSQL and the backend. Docker is optional for local
development; SQLite is the default.

## Principles

Real data only, with every dataset classified (live, modelled, forecast, synthetic); no silent fallback to demo data;
CPCB (not US) AQI; no fake predictions; GPS only after an explicit user action and never stored by default.

## Smart traffic diversions (advisory)

`GET /api/diversion?latitude=&longitude=` scores a 3×3 grid of zones (0.25° spacing) for the next 72 hours. A zone is flagged when wind is low and the boundary layer is shallow (poor ventilation) while modelled PM is elevated or severe. Output is an hour-by-hour strip, forecast windows, and per-zone detail at each window's peak.

Limits: advisory only; modelled (CAMS) PM is coarse so zones often share values; no traffic, emission or road data is used, so no routes are proposed; thresholds in `config/diversion_config.yaml` are **unverified defaults** and must be calibrated by the authority before operational use.

## Safe travel windows (advisory)

`GET /api/activity?latitude=&longitude=` rates each of the next 72 hours as safe / caution / avoid for runners, cyclists and daily commuters, and lists the least-polluted windows between 05:00 and 22:00. The hourly index is the highest CPCB-breakpoint sub-index over single-hour modelled concentrations; it is not the official 24-hour AQI. Per-activity limits live in `config/activity_config.yaml` and are **unverified defaults**, not medical advice. When no hour qualifies as safe, the UI says so and labels the listed windows as only the relatively cleanest. Heat, rain and route-level pollution are not considered.

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

# Configuration

All tunable behaviour lives in `config/*.yaml` and is validated at backend startup
(`backend/app/core/config.py`). An invalid file stops the server with a message listing every problem.

| File | Controls |
|---|---|
| `settings.yaml` | App info, default location, forecast horizons, GPS, refresh/cache, data mode, map, rate limit |
| `model_config.yaml` | Targets, horizons, split, CV, candidate models and parameters, features, seed |
| `simulation_config.yaml` | Slider ranges/defaults, source coefficients, dispersion, uncertainty |
| `aqi_breakpoints.yaml` | CPCB categories, breakpoints, averaging, validity rules |
| `data_sources.yaml` | Weather, air-quality and geocoding providers, endpoints, priorities |

Secrets and deployment values come from environment variables (`.env.example`), never YAML.

The backend exposes `/api/air-quality` and `/api/weather` using the first enabled provider by priority.
Provider errors are returned to the frontend; there is no silent substitution. Open-Meteo air-quality
values are labelled `MODELLED_ESTIMATE`, not sensor observations. Since `ground_stations` is empty,
the AQI shown is an *estimate* from modelled data, never an official CPCB reading. Local ML is trained on that same modelled history (`model_config.yaml`) and is refused below `min_training_rows`. The what-if simulator is labelled
`illustrative_uncalibrated` until its coefficients are calibrated from documented observations.

## Guard rails enforced by validation

- `data_mode.allow_silent_fallback` cannot be `true`: live data is never silently replaced by synthetic data.
- Simulator parameters must satisfy `min <= default <= max`.
- AQI categories must match the six CPCB ranges; breakpoints must increase; all eight pollutants are required.
- Provider URLs must use HTTPS; enabled providers need unique priorities.
- In production, `SECRET_KEY` must not be empty or `change-me`.

## Status flags to keep honest

- `simulation_config.yaml: calibration_status` is `illustrative_uncalibrated`. The UI must show this beside every scenario result until coefficients are fitted to real data.
- `aqi_breakpoints.yaml` is marked **unverified**: confirm against the current CPCB documentation and record the check in `docs/methodology.md`.

## diversion_config.yaml

Grid size/spacing, forecast horizon, stagnation limits (`low_wind_ms`, `poor_ventilation_m2s`), and PM `elevated`/`severe` thresholds. `calibration_status: unverified_defaults` — review before relying on the output.

## activity_config.yaml

Forecast horizon, waking hours, and per-profile `safe_max` / `caution_max` limits on the hourly index. `calibration_status: unverified_defaults` — review before relying on the output.

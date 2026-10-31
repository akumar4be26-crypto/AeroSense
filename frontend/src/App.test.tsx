import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./pages/LocationMap", () => ({ default: () => <div data-testid="location-map" /> }));

const health = { status: "ok", app: "AERIS", version: "0.1.0", environment: "test", time: "2026-10-31T00:00:00Z", database: "ok", config_valid: true };
const config = {
  app: { name: "AERIS", full_name: "x", tagline: "x", version: "0.1.0", timezone: "Asia/Kolkata" },
  default_location: { city: "Patiala", state: "Punjab", country: "India", latitude: 30.353882, longitude: 76.37221 },
  forecast: { durations_hours: [24, 48, 72], interval_hours: 1 },
  gps: { enabled: true, high_accuracy: true, update_interval_ms: 15000, timeout_ms: 15000, maximum_age_ms: 10000, persist_history_default: false },
  refresh: { api_refresh_interval_seconds: 900 },
  data_mode: { default: "live", allow_silent_fallback: false },
  map: { default_zoom: 12, search_radii_km: [1, 3, 5, 10, 20], default_radius_km: 5 },
  simulator: { calibration_status: "illustrative_uncalibrated", parameters: {} },
  aqi_categories: [
    { name: "Good", min: 0, max: 50 },
    { name: "Satisfactory", min: 51, max: 100 },
    { name: "Moderate", min: 101, max: 200 },
    { name: "Poor", min: 201, max: 300 },
    { name: "Very Poor", min: 301, max: 400 },
    { name: "Severe", min: 401, max: 500 },
  ],
};

afterEach(() => vi.unstubAllGlobals());

describe("App", () => {
  it("shows the command center and default location from the API", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => ({
      ok: true,
      json: async () => url.includes("health")
        ? health
        : url.includes("/api/activity")
          ? { as_of: "x", calibration_status: "unverified_defaults", waking_hours: { start: 5, end: 22 }, hours: [{ time: "2026-11-01T08:00", hour: 8, index: 60, category: "Satisfactory", dominant_pollutant: "pm25" }], profiles: { commuter: { label: "Daily commuter", effort: "light", safe_max: 150, caution_max: 250, hours: [{ time: "2026-11-01T08:00", status: "safe" }], safe_hours_waking: 1, best_windows: [{ start: "2026-11-01T08:00", end: "2026-11-01T08:00", mean_index: 60, max_index: 60, category: "Satisfactory", dominant_pollutant: "pm25", status: "safe" }] } }, provider: "open_meteo_air_quality", data_class: "MODELLED_ESTIMATE", limitations: ["Not medical advice test."] }
        : url.includes("/api/diversion")
          ? { as_of: "x", calibration_status: "unverified_defaults", current_zones: [{ id: "r0c0", label: "Centre", row: 0, col: 0, latitude: 0, longitude: 0, tier: "watch", tier_label: "Watch", score: 1, wind_ms: 1, boundary_layer_m: 100, ventilation_m2s: 100, pm25: 50, pm10: 90, no2: 1, co: 1, reasons: [], aqi: 150, aqi_category: "Moderate", dominant_pollutant: "pm25", sub_indices: {}, pollutants: { pm25: 50 } }], current: { time: "2026-11-01T03:00", tier: "watch", label: "Watch" }, hours: [{ time: "2026-11-01T03:00", tier: "watch", label: "Watch" }], windows: [], grid: { size: 3, spacing_deg: 0.25 }, thresholds: { low_wind_ms: 2, poor_ventilation_m2s: 6000, elevated: {}, severe: {} }, air_quality_provider: "open_meteo_air_quality", air_quality_data_class: "MODELLED_ESTIMATE", limitations: ["Advisory decision support only."] }
          : url.includes("/api/aqi")
          ? { aqi: 76, category: "Satisfactory", dominant_pollutant: "pm25", reason: null, as_of: "x", provider: "p", data_class: "MODELLED_ESTIMATE", label: "Estimated CPCB-method AQI computed from modelled data; not an official CPCB station reading." }
          : url.includes("/api/ml/status")
            ? { trained: false, model: null }
            : url.includes("config")
          ? config
          : {
              provider: url.includes("air-quality") ? "open_meteo_air_quality" : "open_meteo_weather",
              data_class: url.includes("air-quality") ? "MODELLED_ESTIMATE" : "WEATHER_FORECAST",
              retrieved_at: "2026-10-31T12:00",
              data: {
                current: { pm2_5: 24, pm10: 42, temperature_2m: 23, wind_speed_10m: 7, relative_humidity_2m: 50, rain: 0 },
                hourly: { time: [], pm2_5: [], pm10: [] },
              },
            },
    })));
    render(<MemoryRouter><App /></MemoryRouter>);
    expect(await screen.findAllByText("Patiala, Punjab")).not.toHaveLength(0);
    expect(screen.getByRole("heading", { name: "Particulate overview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "24h" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Heavy-vehicle diversions" })).toBeInTheDocument();
    expect(await screen.findByText(/Advisory decision support only/)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Safe travel windows" })).toBeInTheDocument();
    expect(await screen.findByText("1 safe hour ahead")).toBeInTheDocument();
    expect(await screen.findByText("Zones by air quality")).toBeInTheDocument();
    expect(await screen.findByText("Satisfactory")).toBeInTheDocument();
    expect(await screen.findByText(/No model trained for this location yet/)).toBeInTheDocument();
  });

  it("reports an unavailable backend honestly", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 503, statusText: "Unavailable", json: async () => ({}) })));
    render(<MemoryRouter><App /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent(/cannot reach its backend/);
  });
});

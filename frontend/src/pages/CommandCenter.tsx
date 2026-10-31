import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  Check,
  Clock3,
  CloudRain,
  Crosshair,
  Droplets,
  Factory,
  Flame,
  HeartPulse,
  Info,
  LocateFixed,
  MapPin,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Thermometer,
  Wind,
} from "lucide-react";
import { useBackendStatus } from "../hooks/useBackendStatus";
import { api } from "../services/api";
import { AqiCard, MlPanel } from "./AqiMl";
import SiteNav from "./SiteNav";
import DiversionPanel from "./DiversionPanel";
import TravelPanel from "./TravelPanel";
import type { ProviderResponse, SimulationResponse } from "../types/api";
const ForecastChart = lazy(() => import("./ForecastChart"));
const LocationMap = lazy(() => import("./LocationMap"));

type LoadState<T> =
  | { phase: "loading" }
  | { phase: "ready"; value: T }
  | { phase: "error"; message: string };

interface Coordinates {
  latitude: number;
  longitude: number;
  source: "default" | "device";
}

const EMPTY: LoadState<ProviderResponse> = { phase: "loading" };
const POLLUTANTS = [
  ["pm2_5", "PM2.5", "µg/m³"],
  ["pm10", "PM10", "µg/m³"],
  ["nitrogen_dioxide", "NO₂", "µg/m³"],
  ["sulphur_dioxide", "SO₂", "µg/m³"],
  ["ozone", "O₃", "µg/m³"],
  ["carbon_monoxide", "CO", "µg/m³"],
] as const;
const DEFAULT_COORDINATES: Coordinates = {
  latitude: 30.353882,
  longitude: 76.37221,
  source: "default",
};

function currentValue(response: ProviderResponse | undefined, key: string): number | undefined {
  const value = response?.data.current?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function formatNumber(value: number | undefined, digits = 0): string {
  return value === undefined ? "—" : value.toFixed(digits);
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "The request failed. Please try again.";
}

function providerLabel(value: string): string {
  return value.replaceAll("_", " ");
}

function SectionHeading({ eyebrow, title, action }: { eyebrow: string; title: string; action?: React.ReactNode }) {
  return (
    <div className="section-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
      </div>
      {action}
    </div>
  );
}

function Metric({ label, value, unit, icon: Icon }: {
  label: string;
  value: string;
  unit?: string;
  icon: typeof Wind;
}) {
  return (
    <div className="metric-card">
      <div className="metric-icon"><Icon size={17} aria-hidden="true" /></div>
      <span className="metric-label">{label}</span>
      <strong>{value}<small>{unit ? ` ${unit}` : ""}</small></strong>
    </div>
  );
}

function ProviderStatus({ response }: { response: LoadState<ProviderResponse> }) {
  if (response.phase === "loading") return <span className="source-label">Loading live provider…</span>;
  if (response.phase === "error") return <span className="source-label source-error">Provider unavailable</span>;
  return <span className="source-label">{providerLabel(response.value.provider)} · {providerLabel(response.value.data_class)}</span>;
}

export default function CommandCenter() {
  const status = useBackendStatus();
  const [coordinates, setCoordinates] = useState(DEFAULT_COORDINATES);
  const [air, setAir] = useState<LoadState<ProviderResponse>>(EMPTY);
  const [weather, setWeather] = useState<LoadState<ProviderResponse>>(EMPTY);
  const [horizon, setHorizon] = useState(24);
  const [refresh, setRefresh] = useState(0);
  const [locationMessage, setLocationMessage] = useState("");
  const [simulationValues, setSimulationValues] = useState<Record<string, number>>({});
  const [simulation, setSimulation] = useState<LoadState<SimulationResponse> | null>(null);

  useEffect(() => {
    if (status.phase !== "ready") return;
    setCoordinates((current) => current.source === "default"
      ? { ...status.config.default_location, source: "default" }
      : current);
    setHorizon(status.config.forecast.durations_hours[0] ?? 24);
    setSimulationValues(Object.fromEntries(
      Object.entries(status.config.simulator.parameters).map(([name, range]) => [name, range.default]),
    ));
  }, [status]);

  const loadData = useCallback(async (signal: AbortSignal) => {
    setAir({ phase: "loading" });
    setWeather({ phase: "loading" });
    const [airResult, weatherResult] = await Promise.allSettled([
      api.airQuality(coordinates.latitude, coordinates.longitude, signal),
      api.weather(coordinates.latitude, coordinates.longitude, signal),
    ]);
    if (signal.aborted) return;
    setAir(airResult.status === "fulfilled"
      ? { phase: "ready", value: airResult.value }
      : { phase: "error", message: errorText(airResult.reason) });
    setWeather(weatherResult.status === "fulfilled"
      ? { phase: "ready", value: weatherResult.value }
      : { phase: "error", message: errorText(weatherResult.reason) });
  }, [coordinates.latitude, coordinates.longitude]);

  useEffect(() => {
    if (status.phase !== "ready") return;
    const controller = new AbortController();
    void loadData(controller.signal);
    const interval = window.setInterval(
      () => void loadData(controller.signal),
      status.config.refresh.api_refresh_interval_seconds * 1000,
    );
    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [loadData, refresh, status]);

  const locateDevice = () => {
    if (!navigator.geolocation) {
      setLocationMessage("This browser does not support device location.");
      return;
    }
    setLocationMessage("Waiting for location permission…");
    const gps = status.phase === "ready" ? status.config.gps : undefined;
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setCoordinates({ latitude: coords.latitude, longitude: coords.longitude, source: "device" });
        setLocationMessage("Using your device location for this session only.");
      },
      (error) => {
        setLocationMessage(error.code === error.PERMISSION_DENIED
          ? "Location permission was denied. You can enable it in your browser settings."
          : error.code === error.TIMEOUT
            ? "Location request timed out. Try again or keep using the default location."
            : "Could not determine your location. You can keep using the default location.");
      },
      {
        enableHighAccuracy: gps?.high_accuracy ?? false,
        timeout: gps?.timeout_ms ?? 15000,
        maximumAge: gps?.maximum_age_ms ?? 10000,
      },
    );
  };

  const runSimulation = async () => {
    setSimulation({ phase: "loading" });
    try {
      setSimulation({ phase: "ready", value: await api.simulate(simulationValues) });
    } catch (error) {
      setSimulation({ phase: "error", message: errorText(error) });
    }
  };

  const pm25 = currentValue(air.phase === "ready" ? air.value : undefined, "pm2_5");
  const temperature = currentValue(weather.phase === "ready" ? weather.value : undefined, "temperature_2m");
  const wind = currentValue(weather.phase === "ready" ? weather.value : undefined, "wind_speed_10m");
  const humidity = currentValue(weather.phase === "ready" ? weather.value : undefined, "relative_humidity_2m");
  const rainfall = currentValue(weather.phase === "ready" ? weather.value : undefined, "rain");
  const weatherUnavailable = weather.phase === "error";
  const healthMessage = pm25 === undefined
    ? "Live particulate estimates are unavailable. Follow local public-health advisories."
    : pm25 >= 60
      ? "Modelled PM2.5 is elevated. Consider limiting strenuous outdoor activity, especially for children, older adults, and people with respiratory conditions."
      : pm25 >= 30
        ? "Modelled PM2.5 is above the lowest CPCB concentration band. Sensitive people may prefer lighter outdoor activity."
        : "Modelled PM2.5 is currently within the lowest CPCB concentration band. Continue to follow local advisories.";

  if (status.phase === "loading") {
    return <main className="app-shell"><div className="loading-screen">Connecting to AERIS…</div></main>;
  }
  if (status.phase === "error") {
    return (
      <main className="app-shell">
        <div className="backend-error" role="alert">
          <AlertTriangle size={22} />
          <div><h1>AERIS cannot reach its backend</h1><p>{status.message}</p><p>Start the backend API, then reload this page.</p></div>
        </div>
      </main>
    );
  }

  const config = status.config;
  const city = coordinates.source === "default"
    ? `${config.default_location.city}, ${config.default_location.state}`
    : "Device location";
  const lastUpdated = air.phase === "ready" ? air.value.retrieved_at : undefined;
  const simulatorGroups = [
    { title: "Emission activity", names: ["firecracker_activity", "traffic_intensity", "industrial_activity", "construction_activity"] },
    { title: "Weather conditions", names: ["wind_speed", "humidity", "rainfall", "temperature"] },
  ];

  return (
    <main className="app-shell">
      <SiteNav mode={config.data_mode.default} live={config.data_mode.default === "live"} onRefresh={() => setRefresh((value) => value + 1)} />

      <section className="welcome-row reveal">
        <div>
          <h1>Air in {coordinates.source === "default" ? config.default_location.city : "your area"}</h1>
          <p className="welcome-copy">Readings come from a satellite-and-model service, not street-level sensors. Each figure says which it is.</p>
        </div>
        <div className="location-control glass">
          <div className="location-name"><MapPin size={16} /><span>{city}</span></div>
          <div className="location-coordinates">{coordinates.latitude.toFixed(4)}° N, {coordinates.longitude.toFixed(4)}° E</div>
          <button type="button" className="text-button" onClick={locateDevice}>
            <LocateFixed size={14} /> Use my location
          </button>
          {locationMessage && <span className="location-message" role="status">{locationMessage}</span>}
        </div>
      </section>

      <div className="dashboard-grid">
        <section id="overview" className="panel air-panel reveal" style={{ "--i": 1 } as React.CSSProperties}>
          <SectionHeading eyebrow="Right now" title="Particulate overview" action={<ProviderStatus response={air} />} />
          {air.phase === "error" ? (
            <div className="inline-error" role="alert"><AlertTriangle size={16} /> {air.message}</div>
          ) : air.phase === "loading" ? (
            <div className="data-loading">Fetching air-quality model…</div>
          ) : (
            <>
              <AqiCard latitude={coordinates.latitude} longitude={coordinates.longitude} refresh={refresh} />
              <div className="pollutant-grid">
                {POLLUTANTS.map(([key, label, unit]) => {
                  const value = currentValue(air.value, key);
                  return (
                    <div className="pollutant-card" key={key}>
                      <span>{label}</span><strong>{formatNumber(value, 1)}</strong><small>{value === undefined ? "Unavailable" : unit}</small>
                    </div>
                  );
                })}
              </div>
              <p className="data-footnote"><Info size={13} /> Modelled estimates are not local sensor measurements.</p>
            </>
          )}
        </section>

        <section id="weather" className="panel weather-panel reveal" style={{ "--i": 2 } as React.CSSProperties}>
          <SectionHeading eyebrow="Outside" title="Weather" action={<CloudRain size={18} className="muted-icon" />} />
          {weather.phase === "loading" && <div className="data-loading">Fetching weather…</div>}
          {weather.phase === "error" && <div className="inline-error" role="alert"><AlertTriangle size={16} /> {weather.message}</div>}
          {weather.phase === "ready" && (
            <>
              <div className="temperature-reading"><Thermometer size={24} /><strong>{formatNumber(temperature, 1)}°</strong><span>current air temperature</span></div>
              <div className="metric-grid">
                <Metric label="Wind" value={formatNumber(wind)} unit="km/h" icon={Wind} />
                <Metric label="Humidity" value={formatNumber(humidity)} unit="%" icon={Droplets} />
                <Metric label="Rain" value={formatNumber(rainfall, 1)} unit="mm" icon={CloudRain} />
              </div>
              <ProviderStatus response={weather} />
            </>
          )}
          {weatherUnavailable && <span className="source-label source-error">Weather data is not being substituted.</span>}
        </section>

        <section id="outlook" className="panel forecast-panel reveal" style={{ "--i": 3 } as React.CSSProperties}>
          <SectionHeading
            eyebrow="Next few days"
            title="Particulate forecast"
            action={(
              <div className="segmented-control" aria-label="Forecast duration">
                {config.forecast.durations_hours.map((hours) => (
                  <button type="button" key={hours} aria-pressed={horizon === hours} onClick={() => setHorizon(hours)}>
                    {hours}h
                  </button>
                ))}
              </div>
            )}
          />
          <div className="chart-legend"><span><i className="legend-dot pm25-dot" /> PM2.5</span><span><i className="legend-dot pm10-dot" /> PM10</span><small>µg/m³</small></div>
          <Suspense fallback={<div className="chart-message">Preparing forecast chart…</div>}>
            <ForecastChart response={air} horizon={horizon} />
          </Suspense>
          <p className="data-footnote"><Clock3 size={13} /> Forecast from a modelled provider; see the trained local forecast below for a validated alternative.</p>
        </section>

        <MlPanel latitude={coordinates.latitude} longitude={coordinates.longitude} />

        <TravelPanel latitude={coordinates.latitude} longitude={coordinates.longitude} refresh={refresh} />

        <DiversionPanel latitude={coordinates.latitude} longitude={coordinates.longitude} refresh={refresh} />

        <section id="map" className="panel map-panel reveal" style={{ "--i": 5 } as React.CSSProperties}>
          <SectionHeading eyebrow="Where" title="Selected area" />
          <div className="map-frame">
            <Suspense fallback={<div className="location-map map-loading">Loading map…</div>}>
              <LocationMap latitude={coordinates.latitude} longitude={coordinates.longitude} zoom={config.map.default_zoom} />
            </Suspense>
            <div className="map-caption"><Crosshair size={14} /> Selected coordinate · no nearby ground stations configured</div>
          </div>
          <div className="map-footer"><span>{city}</span><span>{coordinates.latitude.toFixed(3)}, {coordinates.longitude.toFixed(3)}</span></div>
        </section>

        <section id="advice" className="panel health-panel reveal" style={{ "--i": 6 } as React.CSSProperties}>
          <SectionHeading eyebrow="Advice" title="Health guidance" action={<HeartPulse size={18} className="muted-icon" />} />
          <div className={`health-advice ${pm25 !== undefined && pm25 >= 60 ? "advice-caution" : ""}`}>
            {pm25 !== undefined && pm25 >= 60 ? <AlertTriangle size={19} /> : <ShieldCheck size={19} />}
            <p>{healthMessage}</p>
          </div>
          <p className="data-footnote"><Info size={13} /> Precautionary guidance only. Based on an hourly modelled estimate, not a medical assessment.</p>
        </section>

        <section id="simulator" className="panel simulator-panel reveal" style={{ "--i": 7 } as React.CSSProperties}>
          <SectionHeading eyebrow="Try it" title="Scenario simulator" action={<Sparkles size={18} className="muted-icon" />} />
          <div className="calibration-warning" role="note">
            <AlertTriangle size={17} />
            <span><strong>Illustrative, uncalibrated model.</strong> Results are not forecasts or measured AQI.</span>
          </div>
          <div className="simulator-groups">
            {simulatorGroups.map((group) => (
              <div className="slider-group" key={group.title}>
                <h3>{group.title}</h3>
                {group.names.map((name) => {
                  const range = config.simulator.parameters[name];
                  if (!range) return null;
                  const title = name.replaceAll("_", " ");
                  const Icon = name === "firecracker_activity" ? Flame
                    : name === "traffic_intensity" ? ArrowDownRight
                      : name === "industrial_activity" ? Factory
                        : name === "wind_speed" ? Wind
                          : name === "humidity" ? Droplets
                            : name === "rainfall" ? CloudRain
                              : name === "temperature" ? Thermometer
                                : Activity;
                  const value = simulationValues[name] ?? range.default;
                  return (
                    <label className="slider-row" key={name}>
                      <span className="slider-title"><Icon size={15} /><span>{title}</span><strong>{value} <small>{range.unit}</small></strong></span>
                      <input
                        type="range"
                        min={range.min}
                        max={range.max}
                        step={1}
                        value={value}
                        onChange={(event) => {
                          setSimulationValues((current) => ({ ...current, [name]: Number(event.target.value) }));
                          setSimulation(null);
                        }}
                        aria-label={title}
                      />
                    </label>
                  );
                })}
              </div>
            ))}
          </div>
          <button className="primary-button" type="button" onClick={() => void runSimulation()} disabled={simulation?.phase === "loading"}>
            {simulation?.phase === "loading" ? <RefreshCw size={16} className="spin" /> : <Sparkles size={16} />}
            {simulation?.phase === "loading" ? "Calculating…" : "Run illustrative scenario"}
          </button>
          {simulation?.phase === "error" && <div className="inline-error" role="alert">{simulation.message}</div>}
          {simulation?.phase === "ready" && (
            <div className="simulation-result" aria-live="polite">
              <div className="result-heading"><Check size={16} /> Indicative scenario concentrations</div>
              <div className="result-values">
                {(["pm25", "pm10"] as const).map((key) => (
                  <div key={key}><span>{key === "pm25" ? "PM2.5" : "PM10"}</span><strong>{simulation.value.pollutants[key].value}</strong><small>µg/m³ · illustrative range {simulation.value.pollutants[key].range[0]}–{simulation.value.pollutants[key].range[1]}</small></div>
                ))}
              </div>
              <small>{simulation.value.assumption_label}</small>
            </div>
          )}
        </section>
      </div>

      <footer className="page-footer">
        <span><span className="live-dot" /> {lastUpdated ? `Provider time ${lastUpdated}` : "Waiting for provider data"}</span>
        <span>AERIS v{config.app.version}</span>
      </footer>
    </main>
  );
}

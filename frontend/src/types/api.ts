export interface GPSConfig {
  enabled: boolean;
  high_accuracy: boolean;
  update_interval_ms: number;
  timeout_ms: number;
  maximum_age_ms: number;
  persist_history_default: boolean;
}

export interface PublicConfig {
  app: { name: string; full_name: string; tagline: string; version: string; timezone: string };
  default_location: { city: string; state: string; country: string; latitude: number; longitude: number };
  forecast: { durations_hours: number[]; interval_hours: number };
  gps: GPSConfig;
  refresh: { api_refresh_interval_seconds: number };
  data_mode: { default: "live" | "historical" | "demonstration"; allow_silent_fallback: false };
  map: { default_zoom: number; search_radii_km: number[]; default_radius_km: number };
  simulator: { calibration_status: string; parameters: Record<string, { min: number; default: number; max: number; unit: string }> };
  aqi_categories: Array<{ name: string; min: number; max: number }>;
}

export interface ProviderResponse {
  provider: string;
  data_class: string;
  retrieved_at: string | null;
  data: {
    current?: Record<string, number | string>;
    current_units?: Record<string, string>;
    hourly?: Record<string, Array<number | string>>;
    hourly_units?: Record<string, string>;
  };
}

export interface SimulationResponse {
  calibration_status: string;
  assumption_label: string;
  pollutants: Record<"pm25" | "pm10", { value: number; unit: string; range: [number, number] }>;
  limitations: string;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  app: string;
  version: string;
  environment: string;
  time: string;
  database: "ok" | "unavailable";
  config_valid: boolean;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown };
}

export interface AqiResponse {
  aqi: number | null;
  category: string | null;
  dominant_pollutant: string | null;
  reason: string | null;
  as_of: string | null;
  provider: string;
  data_class: string;
  label: string;
}

export interface MlHorizonResult {
  selected: string;
  skill_vs_persistence: number | null;
  metrics: Record<string, number | null>;
  persistence_metrics: Record<string, number | null>;
}

export interface MlModelSummary {
  model_version: string;
  trained_at: string;
  training_rows: number;
  training_start: string;
  training_end: string;
  data_note: string;
  unavailable_features: string[];
  skipped_candidates: Record<string, string>;
  results: Record<string, MlHorizonResult>;
}

export interface MlStatus {
  trained: boolean;
  model: MlModelSummary | null;
}

export interface MlForecastPoint {
  horizon_hours: number;
  time: string;
  value: number;
  model: string;
  category?: string | null;
}

export interface MlForecast {
  base_time: string;
  forecasts: Record<string, MlForecastPoint[]>;
  metadata_summary: MlModelSummary;
}

export type DiversionTier = "clear" | "watch" | "divert" | "unknown";

export interface DiversionZone {
  id: string;
  label: string;
  row: number;
  col: number;
  latitude: number;
  longitude: number;
  tier: DiversionTier;
  tier_label: string;
  score: number | null;
  wind_ms: number | null;
  boundary_layer_m: number | null;
  ventilation_m2s: number | null;
  pm25: number | null;
  pm10: number | null;
  no2: number | null;
  co: number | null;
  reasons: string[];
  aqi: number | null;
  aqi_category: string | null;
  dominant_pollutant: string | null;
  sub_indices: Record<string, number | null>;
  pollutants: Record<string, number | null>;
}

export interface DiversionWindow {
  start: string;
  end: string;
  hours: number;
  tier: DiversionTier;
  label: string;
  peak_time: string;
  zones: DiversionZone[];
  ranked_zones: string[];
  uniform_pollution: boolean;
  suggested_action: string;
}

export interface DiversionResponse {
  as_of: string;
  calibration_status: string;
  current: { time: string; tier: DiversionTier; label: string } | null;
  current_zones: DiversionZone[];
  hours: { time: string; tier: DiversionTier; label: string }[];
  windows: DiversionWindow[];
  grid: { size: number; spacing_deg: number };
  thresholds: { low_wind_ms: number; poor_ventilation_m2s: number; elevated: Record<string, number>; severe: Record<string, number> };
  air_quality_provider: string;
  air_quality_data_class: string;
  limitations: string[];
}

export type ActivityStatus = "safe" | "caution" | "avoid" | "unknown";

export interface ActivityWindow {
  start: string;
  end: string;
  mean_index: number;
  max_index: number;
  category: string | null;
  dominant_pollutant: string | null;
  status: ActivityStatus;
}

export interface ActivityProfile {
  label: string;
  effort: string;
  safe_max: number;
  caution_max: number;
  hours: { time: string; status: ActivityStatus }[];
  safe_hours_waking: number;
  best_windows: ActivityWindow[];
}

export interface ActivityResponse {
  as_of: string;
  calibration_status: string;
  waking_hours: { start: number; end: number };
  hours: { time: string; hour: number; index: number | null; category: string | null; dominant_pollutant: string | null }[];
  profiles: Record<string, ActivityProfile>;
  provider: string;
  data_class: string;
  limitations: string[];
}

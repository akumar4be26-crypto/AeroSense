import type { ActivityResponse, ApiErrorBody, AqiResponse, DiversionResponse, HealthResponse, MlForecast, MlStatus, ProviderResponse, PublicConfig, SimulationResponse } from "../types/api";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, { signal, headers: { Accept: "application/json" } });
  if (!res.ok) {
    let body: Partial<ApiErrorBody> = {};
    try {
      body = await res.json();
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, body.error?.code ?? `http_${res.status}`, body.error?.message ?? res.statusText);
  }
  return (await res.json()) as T;
}

export const api = {
  health: (signal?: AbortSignal) => get<HealthResponse>("/api/health", signal),
  publicConfig: (signal?: AbortSignal) => get<PublicConfig>("/api/config/public", signal),
  airQuality: (latitude: number, longitude: number, signal?: AbortSignal) =>
    get<ProviderResponse>(`/api/air-quality?latitude=${latitude}&longitude=${longitude}`, signal),
  aqi: (latitude: number, longitude: number, signal?: AbortSignal) =>
    get<AqiResponse>(`/api/aqi?latitude=${latitude}&longitude=${longitude}`, signal),
  diversion: (latitude: number, longitude: number, signal?: AbortSignal) =>
    get<DiversionResponse>(`/api/diversion?latitude=${latitude}&longitude=${longitude}`, signal),
  activity: (latitude: number, longitude: number, signal?: AbortSignal) =>
    get<ActivityResponse>(`/api/activity?latitude=${latitude}&longitude=${longitude}`, signal),
  mlStatus: (latitude: number, longitude: number, signal?: AbortSignal) =>
    get<MlStatus>(`/api/ml/status?latitude=${latitude}&longitude=${longitude}`, signal),
  mlForecast: (latitude: number, longitude: number, signal?: AbortSignal) =>
    get<MlForecast>(`/api/ml/forecast?latitude=${latitude}&longitude=${longitude}`, signal),
  mlTrain: async (latitude: number, longitude: number): Promise<MlStatus> => {
    const response = await fetch(`/api/ml/train?latitude=${latitude}&longitude=${longitude}`, { method: "POST" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof body.detail === "string" ? body.detail : body.error?.message ?? response.statusText;
      throw new ApiError(response.status, `http_${response.status}`, detail);
    }
    return body as MlStatus;
  },
  weather: (latitude: number, longitude: number, signal?: AbortSignal) =>
    get<ProviderResponse>(`/api/weather?latitude=${latitude}&longitude=${longitude}`, signal),
  simulate: async (values: Record<string, number>, signal?: AbortSignal): Promise<SimulationResponse> => {
    const response = await fetch("/api/simulation", {
      method: "POST",
      signal,
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
    if (!response.ok) {
      let body: Partial<ApiErrorBody> = {};
      try {
        body = await response.json();
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(response.status, body.error?.code ?? `http_${response.status}`, body.error?.message ?? response.statusText);
    }
    return response.json() as Promise<SimulationResponse>;
  },
};

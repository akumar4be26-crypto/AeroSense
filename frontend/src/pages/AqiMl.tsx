import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, BrainCircuit, Info } from "lucide-react";
import { api } from "../services/api";
import type { AqiResponse, MlForecast, MlStatus } from "../types/api";

const CATEGORY_CLASS: Record<string, string> = {
  Good: "aqi-good",
  Satisfactory: "aqi-satisfactory",
  Moderate: "aqi-moderate",
  Poor: "aqi-poor",
  "Very Poor": "aqi-very-poor",
  Severe: "aqi-severe",
};

const msg = (error: unknown) => (error instanceof Error ? error.message : "The request failed.");

export function AqiCard({ latitude, longitude, refresh }: { latitude: number; longitude: number; refresh: number }) {
  const [state, setState] = useState<{ aqi?: AqiResponse; error?: string }>({});

  useEffect(() => {
    const controller = new AbortController();
    setState({});
    api.aqi(latitude, longitude, controller.signal)
      .then((aqi) => setState({ aqi }))
      .catch((error) => !controller.signal.aborted && setState({ error: msg(error) }));
    return () => controller.abort();
  }, [latitude, longitude, refresh]);

  if (state.error) return <div className="inline-error" role="alert"><AlertTriangle size={16} /> {state.error}</div>;
  if (!state.aqi) return <div className="data-loading">Computing AQI…</div>;
  const { aqi, category, dominant_pollutant: dominant, reason, label } = state.aqi;
  return (
    <div className={`aqi-callout ${category ? CATEGORY_CLASS[category] ?? "" : ""}`}>
      <div className="aqi-symbol"><strong>{aqi ?? "—"}</strong></div>
      <div>
        <span className="eyebrow">Estimated AQI, CPCB method</span>
        <strong>{category ?? "Not available"}</strong>
        <p>{aqi === null ? reason : `Dominant pollutant: ${dominant?.toUpperCase()}. `}{label}</p>
      </div>
      <Info size={17} className="muted-icon" />
    </div>
  );
}

export function MlPanel({ latitude, longitude }: { latitude: number; longitude: number }) {
  const [status, setStatus] = useState<MlStatus | null>(null);
  const [forecast, setForecast] = useState<MlForecast | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (signal?: AbortSignal) => {
    setError("");
    try {
      const next = await api.mlStatus(latitude, longitude, signal);
      setStatus(next);
      setForecast(next.trained ? await api.mlForecast(latitude, longitude, signal) : null);
    } catch (e) {
      if (!signal?.aborted) setError(msg(e));
    }
  }, [latitude, longitude]);

  useEffect(() => {
    const controller = new AbortController();
    setStatus(null);
    setForecast(null);
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const train = async () => {
    setBusy(true);
    setError("");
    try {
      setStatus(await api.mlTrain(latitude, longitude));
      await load();
    } catch (e) {
      setError(msg(e));
    } finally {
      setBusy(false);
    }
  };

  const model = status?.model;
  return (
    <section id="model" className="panel ml-panel reveal" style={{ "--i": 4 } as React.CSSProperties}>
      <div className="section-heading">
        <div><p className="eyebrow">Our own model</p><h2>Trained forecast</h2></div>
        <BrainCircuit size={18} className="muted-icon" />
      </div>
      {error && <div className="inline-error" role="alert"><AlertTriangle size={16} /> {error}</div>}
      <button type="button" className="text-button" onClick={train} disabled={busy}>
        {busy ? "Training… (about 20 s)" : status?.trained ? "Retrain on latest data" : "Train model for this location"}
      </button>
      {status && !status.trained && <p className="data-footnote">No model trained for this location yet. No predictions are shown until you train one.</p>}
      {forecast && (
        <table className="ml-table">
          <thead><tr><th>Horizon</th><th>AQI</th><th>PM2.5</th><th>PM10</th></tr></thead>
          <tbody>
            {forecast.forecasts.aqi.map((point, i) => (
              <tr key={point.horizon_hours}>
                <td>{point.horizon_hours} h</td>
                <td>{Math.round(point.value)} <small>{point.category}</small></td>
                <td>{forecast.forecasts.pm25?.[i]?.value}</td>
                <td>{forecast.forecasts.pm10?.[i]?.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {model && (
        <>
          <details>
            <summary>Validation vs. persistence baseline (held-out RMSE)</summary>
            <ul className="ml-metrics">
              {Object.entries(model.results).map(([key, r]) => (
                <li key={key}>
                  <strong>{key}</strong>: {r.selected} · RMSE {r.metrics.rmse?.toFixed(1)} vs {r.persistence_metrics.rmse?.toFixed(1)} baseline
                  {r.selected === "persistence" ? " (no model beat the baseline)" : ""}
                </li>
              ))}
            </ul>
          </details>
          <p className="data-footnote"><Info size={13} /> {model.data_note} Trained on {model.training_rows} hourly rows. Not used: {model.unavailable_features.join(", ")} (no real data source).
            {Object.values(model.skipped_candidates).map((note) => ` ${note}.`)}</p>
        </>
      )}
    </section>
  );
}

import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { ActivityResponse, ActivityStatus } from "../types/api";

const STATUS_TEXT: Record<ActivityStatus, string> = { safe: "Safe", caution: "Caution", avoid: "Avoid", unknown: "No data" };
const POLLUTANT: Record<string, string> = { pm25: "PM2.5", pm10: "PM10", no2: "NO₂", so2: "SO₂", co: "CO", o3: "O₃" };

const clock = (iso: string) => new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", hour12: true });
const day = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
const dateKey = (iso: string) => iso.slice(0, 10);

export default function TravelPanel({ latitude, longitude, refresh }: { latitude: number; longitude: number; refresh: number }) {
  const [data, setData] = useState<ActivityResponse | null>(null);
  const [error, setError] = useState("");
  const [profileKey, setProfileKey] = useState("commuter");

  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError("");
    api.activity(latitude, longitude, controller.signal)
      .then(setData)
      .catch((e) => !controller.signal.aborted && setError(e instanceof Error ? e.message : "The request failed."));
    return () => controller.abort();
  }, [latitude, longitude, refresh]);

  const profile = data?.profiles[profileKey];
  const indexByTime = new Map((data?.hours ?? []).map((h) => [h.time, h]));
  const rows = new Map<string, Map<number, { time: string; status: ActivityStatus }>>();
  profile?.hours.forEach((h) => {
    const k = dateKey(h.time);
    if (!rows.has(k)) rows.set(k, new Map());
    rows.get(k)!.set(new Date(h.time).getHours(), h);
  });
  const anySafe = (profile?.safe_hours_waking ?? 0) > 0;
  const summaryStatus: ActivityStatus = !profile ? "unknown" : anySafe ? "safe" : profile.best_windows[0]?.status ?? "avoid";

  return (
    <section id="travel" className="panel travel-panel reveal" style={{ "--i": 4 } as React.CSSProperties}>
      <div className="section-heading">
        <div><p className="eyebrow">Runners, cyclists, commuters</p><h2>Safe travel windows</h2></div>
        {data && <span className="source-label">{data.provider.replaceAll("_", " ")} · {data.data_class.replaceAll("_", " ")}</span>}
      </div>
      <div className="calibration-warning" role="note">
        <span><strong>Not medical advice.</strong> Limits per activity are unverified defaults, and the hourly index is not the official 24-hour AQI.</span>
      </div>
      {error && <div className="inline-error" role="alert">{error}</div>}
      {!data && !error && <div className="data-loading">Finding the cleanest hours…</div>}
      {data && profile && (
        <>
          <div className="segmented-control" role="group" aria-label="Activity">
            {Object.entries(data.profiles).map(([key, p]) => (
              <button key={key} type="button" aria-pressed={profileKey === key} onClick={() => setProfileKey(key)}>{p.label}</button>
            ))}
          </div>

          <div className={`travel-summary st-${summaryStatus}`}>
            <strong>{anySafe ? `${profile.safe_hours_waking} safe ${profile.safe_hours_waking === 1 ? "hour" : "hours"} ahead` : "No safe hours in the next 72 hours"}</strong>
            <span>Safe ≤ {profile.safe_max} · caution ≤ {profile.caution_max} on the hourly index</span>
          </div>

          <h3 className="zone-heading">{anySafe ? "Best times to go" : "Least-polluted times (still not rated safe)"}</h3>
          <ul className="best-list">
            {profile.best_windows.map((w) => (
              <li key={w.start} className={`st-${w.status}`}>
                <strong>{day(w.start)}, {clock(w.start)}{w.start !== w.end && ` – ${clock(w.end)}`}</strong>
                <span>{STATUS_TEXT[w.status]} · index {w.mean_index}{w.category && ` (${w.category})`}</span>
                <br /><small>{w.dominant_pollutant && `Driven by ${POLLUTANT[w.dominant_pollutant] ?? w.dominant_pollutant}`}</small>
              </li>
            ))}
          </ul>

          <div className="heat-rows" role="img" aria-label="Hourly safety by day">
            <div className="heat-row heat-axis"><span />{Array.from({ length: 24 }, (_, h) => <i key={h}>{h % 6 === 0 ? h : ""}</i>)}</div>
            {[...rows.entries()].map(([k, cells]) => (
              <div className="heat-row" key={k}>
                <span>{day(`${k}T00:00`)}</span>
                {Array.from({ length: 24 }, (_, h) => {
                  const c = cells.get(h);
                  const info = c && indexByTime.get(c.time);
                  const asleep = h < data.waking_hours.start || h >= data.waking_hours.end;
                  return <i key={h} className={`${c ? `st-${c.status}` : ""} ${asleep ? "asleep" : ""}`} title={c ? `${clock(c.time)}: ${STATUS_TEXT[c.status]}${info?.index != null ? `, index ${info.index}` : ""}` : undefined} />;
                })}
              </div>
            ))}
          </div>
          <div className="legend-row">
            {(["safe", "caution", "avoid"] as const).map((s) => <span key={s} className={`st-${s}`}><b />{STATUS_TEXT[s]}</span>)}
            <span>Faded hours are outside {clock(`2000-01-01T${String(data.waking_hours.start).padStart(2, "0")}:00`)}–{clock(`2000-01-01T${String(data.waking_hours.end % 24).padStart(2, "0")}:00`)}</span>
          </div>
          <ul className="limit-list">{data.limitations.map((t) => <li key={t}>{t}</li>)}</ul>
        </>
      )}
    </section>
  );
}

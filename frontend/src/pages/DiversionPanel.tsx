import { lazy, Suspense, useEffect, useState } from "react";
import { api } from "../services/api";
import type { DiversionResponse, DiversionWindow, DiversionZone } from "../types/api";

const ZoneMap = lazy(() => import("./ZoneMap"));

const fmtTime = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleString("en-IN", { weekday: "short", hour: "numeric", hour12: true });
};
const num = (v: number | null, digits = 0) => (v === null ? "—" : v.toFixed(digits));

const POLLUTANT_LABEL: Record<string, string> = { pm25: "PM2.5", pm10: "PM10", no2: "NO₂", so2: "SO₂", co: "CO", o3: "O₃" };
const POLLUTANT_UNIT: Record<string, string> = { co: "mg/m³" };
const CATEGORY_ORDER = ["Severe", "Very Poor", "Poor", "Moderate", "Satisfactory", "Good"];
const catClass = (c: string | null) => `cat-${(c ?? "none").toLowerCase().replace(" ", "-")}`;

function ZoneView({ zones, caption, spacingDeg }: { zones: DiversionZone[]; caption: string; spacingDeg: number }) {
  const [colour, setColour] = useState<"aqi" | "tier">("aqi");
  const [view, setView] = useState<"grid" | "map">("grid");
  const size = Math.max(...zones.map((z) => z.row)) + 1;
  const groups = CATEGORY_ORDER.map((c) => ({ c, items: zones.filter((z) => z.aqi_category === c) })).filter((g) => g.items.length);
  const unrated = zones.filter((z) => z.aqi === null);
  return (
    <div className="div-detail">
      <div className="zone-toolbar">
        <div className="segmented-control" role="group" aria-label="Colour zones by">
          <button type="button" aria-pressed={colour === "aqi"} onClick={() => setColour("aqi")}>AQI</button>
          <button type="button" aria-pressed={colour === "tier"} onClick={() => setColour("tier")}>Diversion tier</button>
        </div>
        <div className="segmented-control" role="group" aria-label="Zone display">
          <button type="button" aria-pressed={view === "grid"} onClick={() => setView("grid")}>Grid</button>
          <button type="button" aria-pressed={view === "map"} onClick={() => setView("map")}>Map</button>
        </div>
        <ul className="zone-groups" aria-label="Zones grouped by AQI category">
          {groups.map((g) => (
            <li key={g.c} className={catClass(g.c)}><b>{g.items.length}</b> {g.c}</li>
          ))}
          {unrated.length > 0 && <li className="cat-none"><b>{unrated.length}</b> No AQI</li>}
        </ul>
      </div>
      {view === "map" && (
        <div className="map-frame zone-map-frame">
          <Suspense fallback={<div className="data-loading">Loading map…</div>}>
            <ZoneMap zones={zones} spacingDeg={spacingDeg} colour={colour} />
          </Suspense>
        </div>
      )}
      {view === "grid" && <div className="zone-grid" style={{ gridTemplateColumns: `repeat(${size}, 1fr)` }} role="table" aria-label="Zones, north at top">
        {zones.map((z) => (
          <div key={z.id} role="cell" className={`zone-cell ${colour === "aqi" ? catClass(z.aqi_category) : `tier-${z.tier}`}`} title={z.reasons.join(", ") || "No flags"}>
            <strong>{z.label}</strong>
            {colour === "aqi" ? (
              <>
                <span className="zone-aqi">{z.aqi ?? "—"}</span>
                <span className="zone-cat">{z.aqi_category ?? "Not enough data"}</span>
                {z.dominant_pollutant && <small>Driven by {POLLUTANT_LABEL[z.dominant_pollutant] ?? z.dominant_pollutant}</small>}
              </>
            ) : (
              <>
                <span>{z.tier_label}</span>
                <small>wind {num(z.wind_ms, 1)} m/s · vent. {num(z.ventilation_m2s)}</small>
              </>
            )}
            <dl className="zone-pollutants">
              {Object.entries(z.pollutants).map(([k, v]) => (
                <div key={k} className={k === z.dominant_pollutant ? "dominant" : ""}>
                  <dt>{POLLUTANT_LABEL[k] ?? k}</dt>
                  <dd>{v === null ? "—" : v}</dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>}
      <p className="data-footnote">{caption} North is at the top; the map shows each zone as a square of about {Math.round(spacingDeg * 111)} km. Pollutant values are in µg/m³ (CO in {POLLUTANT_UNIT.co}).</p>
    </div>
  );
}

function WindowDetail({ window, spacingDeg }: { window: DiversionWindow; spacingDeg: number }) {
  return (
    <>
      <ZoneView zones={window.zones} caption={`Peak hour: ${fmtTime(window.peak_time)}.`} spacingDeg={spacingDeg} />
      {window.uniform_pollution && <p className="data-footnote">Modelled particulates are nearly the same across zones; differences come from wind and mixing height.</p>}
    </>
  );
}

export default function DiversionPanel({ latitude, longitude, refresh }: { latitude: number; longitude: number; refresh: number }) {
  const [data, setData] = useState<DiversionResponse | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(0);
  const [when, setWhen] = useState<"now" | "peak">("now");

  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError("");
    setSelected(0);
    api.diversion(latitude, longitude, controller.signal)
      .then(setData)
      .catch((e) => !controller.signal.aborted && setError(e instanceof Error ? e.message : "The request failed."));
    return () => controller.abort();
  }, [latitude, longitude, refresh]);

  const current = data?.current;
  const win = data?.windows[selected];
  return (
    <section id="diversions" className="panel diversion-panel reveal" style={{ "--i": 5 } as React.CSSProperties}>
      <div className="section-heading">
        <div><p className="eyebrow">For traffic authorities</p><h2>Heavy-vehicle diversions</h2></div>
        {data && <span className="source-label">{data.air_quality_provider.replaceAll("_", " ")} · {data.air_quality_data_class.replaceAll("_", " ")}</span>}
      </div>
      <div className="calibration-warning" role="note">
        <span><strong>Advisory only.</strong> Thresholds are unverified defaults, and no traffic or road data is used, so no routes are proposed.</span>
      </div>
      {error && <div className="inline-error" role="alert">{error}</div>}
      {!data && !error && <div className="data-loading">Assessing the next 72 hours…</div>}
      {data && current && (
        <>
          <div className={`div-status tier-${current.tier}`}>
            <span className="eyebrow">Right now, anywhere in the area</span>
            <strong>{current.label}</strong>
          </div>
          <div className="hour-strip" role="img" aria-label="Hourly diversion tier for the next 72 hours">
            {data.hours.map((h) => <i key={h.time} className={`tier-${h.tier}`} title={`${fmtTime(h.time)}: ${h.label}`} />)}
          </div>
          <div className="hour-strip-legend"><span>{fmtTime(data.hours[0].time)}</span><span>{fmtTime(data.hours[data.hours.length - 1].time)}</span></div>

          <h3 className="zone-heading">Zones by air quality</h3>
          <div className="segmented-control" role="group" aria-label="Zone time">
            <button type="button" aria-pressed={when === "now"} onClick={() => setWhen("now")}>Now</button>
            <button type="button" aria-pressed={when === "peak"} disabled={!win} onClick={() => setWhen("peak")}>Window peak</button>
          </div>
          {when === "peak" && win ? (
            <WindowDetail window={win} spacingDeg={data.grid.spacing_deg} />
          ) : (
            <ZoneView zones={data.current_zones} caption="Current hour." spacingDeg={data.grid.spacing_deg} />
          )}

          {data.windows.length === 0 ? (
            <p className="data-footnote">No watch or diversion windows in the next 72 hours under the current thresholds.</p>
          ) : (
            <div className="div-body">
              <ul className="window-list" aria-label="Forecast windows">
                {data.windows.map((w, i) => (
                  <li key={w.start}>
                    <button type="button" className={`window-item tier-${w.tier}`} aria-pressed={selected === i} onClick={() => setSelected(i)}>
                      <strong>{w.label}</strong>
                      <span>{fmtTime(w.start)} → {fmtTime(w.end)}</span>
                      <small>{w.hours} h</small>
                    </button>
                  </li>
                ))}
              </ul>
              {win && (
                <div>
                  <p className="div-action">{win.suggested_action}</p>
                </div>
              )}
            </div>
          )}
          <ul className="limit-list">{data.limitations.map((text) => <li key={text}>{text}</li>)}</ul>
        </>
      )}
    </section>
  );
}

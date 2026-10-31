import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ProviderResponse } from "../types/api";

type LoadState<T> =
  | { phase: "loading" }
  | { phase: "ready"; value: T }
  | { phase: "error"; message: string };

export default function ForecastChart({ response, horizon }: { response: LoadState<ProviderResponse>; horizon: number }) {
  const points = useMemo(() => {
    if (response.phase !== "ready") return [];
    const hourly = response.value.data.hourly;
    const times = hourly?.time;
    const pm25 = hourly?.pm2_5;
    const pm10 = hourly?.pm10;
    if (!times || !pm25 || !pm10) return [];
    const currentTime = Date.parse(String(response.value.data.current?.time ?? ""));
    return times.flatMap((time, index) => {
      if (Date.parse(String(time)) < currentTime) return [];
      return [{
        time: new Date(String(time)).toLocaleTimeString([], { hour: "numeric", timeZone: "Asia/Kolkata" }),
        pm25: typeof pm25[index] === "number" ? pm25[index] : null,
        pm10: typeof pm10[index] === "number" ? pm10[index] : null,
      }];
    }).slice(0, horizon);
  }, [horizon, response]);

  if (response.phase === "loading") return <div className="chart-message">Loading forecast…</div>;
  if (response.phase === "error") return <div className="chart-message" role="alert">{response.message}</div>;
  if (!points.length) return <div className="chart-message">This provider did not return hourly particulate estimates.</div>;

  return (
    <div className="chart-wrap" role="img" aria-label={`${horizon}-hour modelled particulate forecast`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#cdc4b2" vertical={false} />
          <XAxis dataKey="time" tick={{ fill: "#6a6358", fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={24} />
          <YAxis tick={{ fill: "#6a6358", fontSize: 10 }} tickLine={false} axisLine={false} width={34} />
          <Tooltip
            contentStyle={{ background: "#f3eee4", border: "1px solid #1f1c18", borderRadius: 0, color: "#1f1c18" }}
            formatter={(value) => [`${value ?? "—"} µg/m³`, ""]}
          />
          <Line type="monotone" dataKey="pm25" name="PM2.5" stroke="#a8341a" strokeWidth={2.5} dot={false} connectNulls />
          <Line type="monotone" dataKey="pm10" name="PM10" stroke="#1f1c18" strokeWidth={2} dot={false} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

import { MapContainer, Rectangle, TileLayer, Tooltip } from "react-leaflet";
import type { DiversionZone } from "../types/api";

const AQI_COLOURS: Record<string, string> = {
  Good: "#2f7d4f", Satisfactory: "#6c8f22", Moderate: "#a77d0a",
  Poor: "#c25a12", "Very Poor": "#a8341a", Severe: "#7a1a2b",
};
const TIER_COLOURS: Record<string, string> = { clear: "#2f7d4f", watch: "#a77d0a", divert: "#a8341a" };
const NEUTRAL = "#7a7468";

export default function ZoneMap({ zones, spacingDeg, colour }: { zones: DiversionZone[]; spacingDeg: number; colour: "aqi" | "tier" }) {
  const half = spacingDeg / 2;
  const lats = zones.map((z) => z.latitude);
  const lons = zones.map((z) => z.longitude);
  const bounds: [[number, number], [number, number]] = [
    [Math.min(...lats) - half, Math.min(...lons) - half],
    [Math.max(...lats) + half, Math.max(...lons) + half],
  ];
  return (
    <MapContainer bounds={bounds} boundsOptions={{ padding: [24, 24] }} scrollWheelZoom={false} className="location-map zone-map" aria-label="Map of the nine assessment zones">
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {zones.map((z) => {
        const fill = (colour === "aqi" ? AQI_COLOURS[z.aqi_category ?? ""] : TIER_COLOURS[z.tier]) ?? NEUTRAL;
        return (
          <Rectangle
            key={z.id}
            bounds={[[z.latitude - half, z.longitude - half], [z.latitude + half, z.longitude + half]]}
            pathOptions={{ color: fill, weight: 2, fillColor: fill, fillOpacity: 0.4 }}
          >
            <Tooltip sticky>
              <strong>{z.label}</strong><br />
              {colour === "aqi" ? `AQI ${z.aqi ?? "—"} · ${z.aqi_category ?? "Not enough data"}` : z.tier_label}
            </Tooltip>
          </Rectangle>
        );
      })}
    </MapContainer>
  );
}

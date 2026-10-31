import { useEffect } from "react";
import { CircleMarker, MapContainer, TileLayer, useMap } from "react-leaflet";

interface LocationMapProps {
  latitude: number;
  longitude: number;
  zoom: number;
}

function Recenter({ latitude, longitude, zoom }: LocationMapProps) {
  const map = useMap();
  useEffect(() => {
    map.setView([latitude, longitude], zoom, { animate: true });
  }, [latitude, longitude, map, zoom]);
  return null;
}

export default function LocationMap({ latitude, longitude, zoom }: LocationMapProps) {
  const center: [number, number] = [latitude, longitude];

  return (
    <MapContainer
      center={center}
      zoom={zoom}
      scrollWheelZoom={false}
      className="location-map"
      aria-label="Map showing the selected location"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Recenter latitude={latitude} longitude={longitude} zoom={zoom} />
      <CircleMarker
        center={center}
        radius={9}
        pathOptions={{ color: "#7cf2c1", fillColor: "#16b981", fillOpacity: 0.9, weight: 3 }}
      />
    </MapContainer>
  );
}

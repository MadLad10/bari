import { useMemo } from "react";
import GeoMap from "./GeoMap";

export default function LocationPicker({ latitude, longitude, onChange }) {
  const points = useMemo(() => latitude !== "" && longitude !== "" && latitude != null && longitude != null
    && Number.isFinite(Number(latitude)) && Number.isFinite(Number(longitude)) ? [{ latitude: Number(latitude), longitude: Number(longitude), title: "Property location" }] : [], [latitude, longitude]);
  return <section className="pin-picker"><h3>Property map pin</h3><p className="geo-help">Click the map or enter coordinates for the building. Nearby distances and routes use this pin. Leave both empty if you cannot confirm the location.</p>
    <GeoMap points={points} onPick={onChange} label="Choose property location" />
    <div className="pin-fields"><label>Latitude<input type="number" min="-90" max="90" step="any" value={latitude ?? ""} onChange={e => onChange({ latitude: e.target.value, longitude })} /></label>
      <label>Longitude<input type="number" min="-180" max="180" step="any" value={longitude ?? ""} onChange={e => onChange({ latitude, longitude: e.target.value })} /></label></div>
    <button type="button" className="od-button secondary" onClick={() => onChange({ latitude: "", longitude: "" })}>Clear map pin</button>
  </section>;
}

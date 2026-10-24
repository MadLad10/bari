import { useEffect, useMemo, useRef, useState } from "react";
import { fetchNearby, fetchRoute } from "../api";
import GeoMap from "./GeoMap";

const kinds = [["hospital", "Hospital", "🏥"], ["bus_stop", "Bus stop", "🚌"], ["market", "Market / supermarket", "🛒"]];
const distance = meters => meters < 1000 ? `${meters} m` : `${(meters / 1000).toFixed(2)} km`;

export default function PropertyLocation({ property }) {
  const [nearby, setNearby] = useState(null), [route, setRoute] = useState(null), [error, setError] = useState("");
  const [loading, setLoading] = useState(false), [routing, setRouting] = useState(false);
  const [selection, setSelection] = useState({});
  const generation = useRef(0);
  const hasPin = Number.isFinite(property.latitude) && Number.isFinite(property.longitude);
  useEffect(() => { generation.current++; setNearby(null); setRoute(null); setError(""); setSelection({}); setLoading(false); setRouting(false); return () => { generation.current++; }; }, [property.id, property.latitude, property.longitude]);
  const points = useMemo(() => hasPin ? [{ latitude: property.latitude, longitude: property.longitude, title: property.title },
    ...(nearby ? Object.values(nearby.categories).flat().map(p => ({ ...p, destination: true })) : [])] : [], [hasPin, property.latitude, property.longitude, property.title, nearby]);
  async function load() {
    const current = generation.current;
    setLoading(true); setError(""); setRoute(null);
    try { const result = await fetchNearby(property.id); if (current === generation.current) { setNearby(result); setSelection({}); } }
    catch (e) { if (current === generation.current) setError(e.message); }
    finally { if (current === generation.current) setLoading(false); }
  }
  async function showRoute(destinationId) {
    const current = generation.current;
    setRouting(true); setError(""); setRoute(null);
    try { const result = await fetchRoute(property.id, destinationId); if (current === generation.current) setRoute(result); }
    catch (e) { if (current === generation.current) setError(e.message); }
    finally { if (current === generation.current) setRouting(false); }
  }
  return <div className="detail-section">
    <h2>Location &amp; accessibility</h2>
    {hasPin ? <GeoMap points={points} geometry={route?.geometry} label="Property, nearby places and route" /> : <p className="geo-error">This listing has no map pin yet. Ask the owner to add its location before nearby distances or routes can be calculated.</p>}
    <p className="geo-help">Distances start at the listing’s supplied map pin. Nearby places come from OpenStreetMap and may be incomplete. Distances below are straight-line distances; choose a road route for driving distance.</p>
    <div className="geo-actions"><button type="button" disabled={!hasPin || loading || routing} onClick={load}>{loading ? "Finding nearby places…" : nearby ? "Reload nearby places" : "Find nearby places"}</button>
      {hasPin && <a className="map-open-link" target="_blank" rel="noreferrer" href={`https://www.openstreetmap.org/?mlat=${property.latitude}&mlon=${property.longitude}#map=16/${property.latitude}/${property.longitude}`}>Open location in OpenStreetMap ↗</a>}</div>
    {error && <p className="geo-error" role="alert">{error}</p>}
    <div className="nearby-grid">
      <div className="nearby-card"><span className="nearby-icon">🎓</span><span className="nearby-label">University</span><strong className="nearby-name">{property.nearby_university || "Not specified"}</strong><span className="nearby-value">{property.university_distance_km != null ? `${property.university_distance_km.toFixed(1)} km · listing supplied` : "Distance not supplied"}</span></div>
      {kinds.map(([key, label, icon]) => {
        const places = nearby?.categories[key] || [];
        const selected = places.find(p => p.id === selection[key]) || places[0];
        return <div className="nearby-card" key={key}><span className="nearby-icon">{icon}</span><span className="nearby-label">{label}</span>
          {!nearby ? <span className="nearby-value">{loading ? "Loading…" : "Find nearby places to load"}</span> : !selected ? <span className="nearby-value">None mapped within 3 km</span> : <>
            <label className="nearby-name">Choose {label.toLowerCase()}<select aria-label={`Choose ${label.toLowerCase()}`} value={selected.id} onChange={e => { setSelection(p => ({ ...p, [key]: e.target.value })); setRoute(null); }}>{places.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
            <strong className="nearby-value">{distance(selected.distance_m)} straight line</strong><a href={selected.osm_url} target="_blank" rel="noreferrer">View mapped place ↗</a>
            <button type="button" disabled={routing || loading} onClick={() => showRoute(selected.id)}>{routing ? "Loading route…" : `Road route to ${label.toLowerCase()}`}</button>
          </>}
        </div>;
      })}
    </div>
    {route && <div className="route-summary" role="status"><strong>Driving route to {route.destination.name}</strong><p>{distance(route.distance_m)} by road · about {Math.max(1, Math.round(route.duration_s / 60))} min</p><p>Estimated driving time without live traffic. The route is drawn in blue on the map.</p></div>}
    {nearby && <p className="geo-help">© OpenStreetMap contributors · ODbL. Road routes: OSRM. Nearby results are cached for up to 24 hours.</p>}
  </div>;
}

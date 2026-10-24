import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./GeoMap.css";

export default function GeoMap({ points = [], geometry, onPick, label = "Property map" }) {
  const root = useRef(null), map = useRef(null), layer = useRef(null), picker = useRef(onPick);
  picker.current = onPick;
  useEffect(() => {
    const instance = L.map(root.current, { scrollWheelZoom: false }).setView([23.78, 90.4], 12);
    map.current = instance;
    L.tileLayer(import.meta.env.VITE_MAP_TILE_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', maxZoom: 19,
    }).addTo(instance);
    layer.current = L.featureGroup().addTo(instance);
    instance.on("click", e => picker.current?.({ latitude: Number(e.latlng.lat.toFixed(6)), longitude: Number(e.latlng.lng.toFixed(6)) }));
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => instance.invalidateSize()) : null;
    observer?.observe(root.current);
    return () => { observer?.disconnect(); instance.remove(); map.current = null; layer.current = null; };
  }, []);
  useEffect(() => {
    if (!layer.current) return;
    layer.current.clearLayers();
    for (const point of points) {
      if (!Number.isFinite(point.latitude) || !Number.isFinite(point.longitude)) continue;
      const popup = document.createElement("div");
      const title = document.createElement("strong"); title.textContent = point.title || point.name || "Property pin"; popup.appendChild(title);
      if (point.price != null) { const price = document.createElement("p"); price.textContent = `৳${Number(point.price).toLocaleString()}${point.listing_type === "sale" ? "" : ` / ${point.rental_type || "month"}`}`; popup.appendChild(price); }
      if (point.propertyId) { const link = document.createElement("a"); link.href = `/property/${point.propertyId}`; link.textContent = "View property →"; popup.appendChild(link); }
      const marker = L.circleMarker([point.latitude, point.longitude], { radius: point.destination ? 9 : 8,
        color: "#fff", weight: 2, fillColor: point.destination ? "#b46b32" : "#24573a", fillOpacity: 1 }).bindPopup(popup);
      const tooltip = document.createElement("span"); tooltip.textContent = point.title || point.name || "Property pin";
      marker.bindTooltip(tooltip).addTo(layer.current);
      const element = marker.getElement();
      element?.setAttribute("tabindex", "0"); element?.setAttribute("role", "button");
      element?.setAttribute("aria-label", `Map pin: ${tooltip.textContent}`);
      element?.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); marker.openPopup(); } });
    }
    if (geometry) L.geoJSON(geometry, { style: { color: "#2563eb", weight: 5, opacity: .85 } }).addTo(layer.current);
    const bounds = layer.current.getBounds();
    if (bounds.isValid()) map.current.fitBounds(bounds.pad(.15), { maxZoom: 16, animate: false });
  }, [points, geometry]);
  return <div ref={root} className="geo-map" role="region" aria-label={label} />;
}

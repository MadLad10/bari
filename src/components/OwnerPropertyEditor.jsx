import { useEffect, useRef, useState } from "react";
import { updateProperty } from "../api";

const NUMBERS = ["price", "bedrooms", "bathrooms", "area_sqft", "university_distance_km"];
const FIELDS = ["title", "description", "property_type", "listing_type", "rental_type", "furnishing", "price",
  "bedrooms", "bathrooms", "area_sqft", "address", "area", "city", "nearby_university", "university_distance_km",
  "owner_name", "owner_phone", "owner_email", "is_female_only", "has_furniture_for_sale"];

export default function OwnerPropertyEditor({ property, onClose, onSaved }) {
  const dialog = useRef(null);
  const [form, setForm] = useState(() => Object.fromEntries(FIELDS.map(k => [k, property[k] ?? ""])));
  const [amenities, setAmenities] = useState((property.amenities || []).join(", "));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => { dialog.current.showModal(); }, []);
  const change = e => setForm(p => ({ ...p, [e.target.name]: e.target.type === "checkbox" ? e.target.checked : e.target.value,
    ...(e.target.name === "listing_type" && e.target.value !== "sale" && !p.rental_type ? { rental_type: "monthly" } : {}) }));
  const input = (name, label, props = {}) => <label className="od-field" key={name}>
    <span>{label}</span><input name={name} value={form[name]} onChange={change} {...props} />
  </label>;
  const select = (name, label, values) => <label className="od-field" key={name}><span>{label}</span>
    <select name={name} aria-label={label} value={form[name]} onChange={change}>{values.map(v => <option key={v} value={v}>{v.replaceAll("_", " ")}</option>)}</select>
  </label>;
  async function save(e) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const normalized = { ...form };
      NUMBERS.forEach(k => { normalized[k] = form[k] === "" ? null : Number(form[k]); });
      ["owner_email", "nearby_university"].forEach(k => { normalized[k] = form[k] || null; });
      normalized.rental_type = form.listing_type === "sale" ? null : (form.rental_type || "monthly");
      normalized.amenities = amenities.split(",").map(s => s.trim()).filter(Boolean);
      const changed = Object.fromEntries(Object.entries(normalized).filter(([k, v]) => JSON.stringify(v) !== JSON.stringify(property[k] ?? (v === null ? null : ""))));
      await updateProperty(property.id, changed);
      await onSaved();
      onClose();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  return <dialog ref={dialog} className="od-dialog" aria-labelledby="edit-property-title" onCancel={e => { if (busy) e.preventDefault(); else onClose(); }}>
    <form onSubmit={save}>
      <div className="od-panel-heading"><div><span className="od-eyebrow">PROPERTY DETAILS</span><h2 id="edit-property-title">Edit listing</h2></div>
        <button type="button" className="od-icon-button" onClick={onClose} disabled={busy} aria-label="Close editor">×</button></div>
      <p className="od-muted">Changes to the owner name or location require fresh document checks.</p>
      <fieldset disabled={busy}>
        {input("title", "Listing title", { required: true, minLength: 5, maxLength: 200 })}
        <label className="od-field"><span>Description</span><textarea name="description" value={form.description} onChange={change} required minLength={20} rows={4} /></label>
        <div className="od-form-grid">
          {select("property_type", "Property type", ["apartment", "house", "office", "room"])}
          {select("listing_type", "Listing type", ["rent", "sale", "sublet"])}
          {form.listing_type !== "sale" && select("rental_type", "Rental period", ["monthly", "daily", "hourly"])}
          {select("furnishing", "Furnishing", ["furnished", "semi_furnished", "unfurnished"])}
          {input("price", form.listing_type === "sale" ? "Sale price (BDT)" : "Price per rental period (BDT)", { type: "number", required: true, min: "0.01", step: "0.01" })}
          {input("bedrooms", "Bedrooms", { type: "number", required: true, min: 0 })}
          {input("bathrooms", "Bathrooms", { type: "number", required: true, min: 0 })}
          {input("area_sqft", "Floor area (sq ft)", { type: "number", min: 1 })}
        </div>
        {input("address", "Full address", { required: true, minLength: 5, maxLength: 300 })}
        <div className="od-form-grid">
          {input("area", "Neighborhood", { required: true, minLength: 2, maxLength: 100 })}
          {input("city", "City", { required: true, minLength: 2, maxLength: 100 })}
          {input("nearby_university", "Nearby university", { maxLength: 200 })}
          {input("university_distance_km", "Distance to university (km)", { type: "number", min: 0, step: "0.1" })}
        </div>
        <label className="od-field"><span>Amenities (separated by commas)</span><input value={amenities} onChange={e => setAmenities(e.target.value)} placeholder="WiFi, Lift, Parking" /></label>
        <label className="od-check"><input type="checkbox" name="is_female_only" checked={!!form.is_female_only} onChange={change} />Women-only accommodation</label>
        <p className="od-muted">Women-only listings need separate admin safety approval. Changes to safety details, photos, occupancy or owner contacts require a fresh review.</p>
        <label className="od-check"><input type="checkbox" name="has_furniture_for_sale" checked={!!form.has_furniture_for_sale} onChange={change} />Offer furniture for sale with the rental</label>
        <h3>Owner contact</h3>
        {input("owner_name", "Owner name", { required: true, minLength: 2, maxLength: 100 })}
        <div className="od-form-grid">
          {input("owner_phone", "Phone number", { required: true, minLength: 11, maxLength: 20 })}
          {input("owner_email", "Email address", { type: "email" })}
        </div>
      </fieldset>
      {error && <p className="od-error" role="alert">{error}</p>}
      <div className="od-dialog-actions"><button type="button" className="od-button secondary" disabled={busy} onClick={onClose}>Cancel</button>
        <button className="od-button" disabled={busy}>{busy ? "Saving…" : "Save changes"}</button></div>
    </form>
  </dialog>;
}

import { useState } from "react";
import { API_ROOT, updateProperty, uploadPhoto } from "../api";

export const photoUrl = url => url?.startsWith("/") ? `${API_ROOT}${url}` : url;

export default function OwnerPhotos({ property, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  async function upload(e) {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    setBusy(true); setError(null);
    try {
      for (const file of files) {
        if (file.size > 10 * 1024 * 1024) throw new Error("Each photo must be under 10 MB.");
        await uploadPhoto(property.id, file);
      }
    } catch (e) { setError(e.message); }
    finally { await onChanged(); setBusy(false); }
  }
  async function remove(index) {
    setBusy(true); setError(null);
    try { await updateProperty(property.id, { photos: property.photos.filter((_, i) => i !== index) }); await onChanged(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  return <section className="od-photos"><h3>Property photos</h3><p className="od-muted">The first image is your listing’s cover. JPEG, PNG or WebP, up to 10 MB each.</p>
    <div className="od-photo-grid">{property.photos.map((url, i) => <div key={`${url}-${i}`}><img src={photoUrl(url)} alt={`Property photo ${i + 1}`} loading="lazy" />
      <button className="od-button secondary" disabled={busy} onClick={() => remove(i)} aria-label={`Remove photo ${i + 1}`}>Remove</button></div>)}</div>
    <label className="od-upload">{busy ? "Updating photos…" : "+ Add photos"}<input type="file" accept="image/jpeg,image/png,image/webp" multiple disabled={busy} onChange={upload} /></label>
    {error && <p className="od-error" role="alert">{error}</p>}
  </section>;
}

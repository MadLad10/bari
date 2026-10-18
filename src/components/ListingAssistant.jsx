import { useState } from "react";
import { Link } from "react-router-dom";
import { listingAssistant } from "../api";
import "./ListingAssistant.css";

const VERDICT = {
  suspiciously_low: { label: "Far below similar listings", tone: "warn", hint: "Listings priced far below the market are held for review as possible scams. Double-check the price." },
  below_typical: { label: "Below typical", tone: "ok", hint: "Cheaper than most similar places, so it should attract interest." },
  typical: { label: "In the typical range", tone: "ok", hint: "Priced like similar listings nearby." },
  above_typical: { label: "Above typical", tone: "info", hint: "Pricier than most similar places. Highlight what justifies it." },
  unknown: { label: "Not enough similar listings", tone: "info", hint: "Add the area and university for a price comparison." },
};

function toDraft(form) {
  const num = (v) => (v === "" || v == null ? null : Number(v));
  return {
    ...form,
    price: num(form.price),
    bedrooms: num(form.bedrooms),
    bathrooms: num(form.bathrooms),
    area_sqft: num(form.area_sqft),
    university_distance_km: num(form.university_distance_km),
    nearby_university: form.nearby_university || null,
    rental_type: form.listing_type === "sale" ? null : form.rental_type,
    safety_score: undefined,
    owner_name: undefined, owner_phone: undefined, owner_email: undefined,
  };
}

export default function ListingAssistant({ form, photos = [], onUseDescription }) {
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [language, setLanguage] = useState("en");

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setResult(await listingAssistant({ ...toDraft(form), photos: photos.map((p) => p.url), language }));
    } catch (e) {
      setError(e.status === 403 ? "Log in with an owner account to use the assistant." : e.message);
    } finally {
      setBusy(false);
    }
  }

  const v = result && VERDICT[result.price_check.verdict];
  const stats = result?.price_check.stats;

  return (
    <aside className="la-panel" aria-label="Listing assistant">
      <div className="la-head">
        <span className="la-icon">✦</span>
        <div>
          <div className="la-title">Listing assistant</div>
          <div className="la-sub">Description draft, missing info and a price check</div>
        </div>
      </div>
      <div className="la-controls">
        <select value={language} onChange={(e) => setLanguage(e.target.value)} aria-label="Description language">
          <option value="en">English</option>
          <option value="bn">বাংলা</option>
        </select>
        <button type="button" onClick={run} disabled={busy}>{busy ? "Reviewing…" : result ? "Review again" : "Review my listing"}</button>
      </div>
      {error && <div className="la-error">{error}</div>}

      {result && (
        <>
          <div className="la-section">
            <h4>Suggested description</h4>
            <p className="la-desc">{result.description}</p>
            <button type="button" className="la-use" onClick={() => onUseDescription(result.description)}>Use this description</button>
            {result.description_source === "template" && <p className="la-note">AI unavailable, so this is a basic template.</p>}
          </div>

          <div className="la-section">
            <h4>Missing or weak info</h4>
            {result.missing_info.length === 0 ? <p className="la-good">Looks complete.</p> : (
              <ul className="la-missing">
                {result.missing_info.map((m, i) => (
                  <li key={i} className={m.severity}><span>{m.severity === "required" ? "Required" : "Tip"}</span>{m.message}</li>
                ))}
              </ul>
            )}
          </div>

          <div className="la-section">
            <h4>Price check</h4>
            <div className={`la-verdict ${v.tone}`}>{v.label}</div>
            <p className="la-note">{v.hint}</p>
            {stats && (
              <p className="la-stats">
                {stats.n} similar listings: median ৳{Math.round(stats.median).toLocaleString()},
                typical range ৳{Math.round(stats.p25).toLocaleString()}–৳{Math.round(stats.p75).toLocaleString()}
              </p>
            )}
            {result.price_check.comparables.length > 0 && (
              <ul className="la-comps">
                {result.price_check.comparables.slice(0, 5).map((c) => (
                  <li key={c.id}>
                    <Link to={`/property/${c.id}`} target="_blank">{c.title}</Link>
                    <span>৳{Number(c.price).toLocaleString()} · {c.area}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </aside>
  );
}

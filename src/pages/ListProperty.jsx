import { useState, useRef, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createProperty, uploadPhoto, uploadDocument } from "../api";
import NavAuth from "../auth/NavAuth";
import { useAuth } from "../auth/AuthContext";
import { API_ROOT } from "../api";
import ListingAssistant from "../components/ListingAssistant";
import "./ListProperty.css";

const UNIVERSITIES = [
  "BRAC University", "North South University", "Dhaka University", "BUET", "IUB",
  "AIUB", "East West University", "Jahangirnagar University", "Other",
];

const AMENITY_OPTIONS = [
  "AC", "WiFi", "Gas", "Generator", "Lift", "Parking",
  "CCTV", "Security Guard", "Rooftop", "Attached Bath",
  "Study Room", "Common Kitchen", "Water Reservoir",
];

const STEPS = ["Property Info", "Location & University", "Owner Details", "Photos & Docs"];

const INITIAL = {
  title: "",
  description: "",
  property_type: "apartment",
  listing_type: "rent",
  rental_type: "monthly",
  furnishing: "unfurnished",
  price: "",
  bedrooms: "1",
  bathrooms: "1",
  area_sqft: "",
  address: "",
  area: "",
  city: "Dhaka",
  nearby_university: "",
  university_distance_km: "",
  is_female_only: false,
  safety_score: "",
  amenities: [],
  has_furniture_for_sale: false,
  owner_name: "",
  owner_phone: "",
  owner_email: "",
};

export default function ListProperty() {
  const navigate = useNavigate();
  const { user, ready, openAuth } = useAuth();
  const [form, setForm] = useState(INITIAL);
  const [step, setStep] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [createdId, setCreatedId] = useState(null);
  const [photos, setPhotos] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const photoInputRef = useRef(null);
  const docInputRef = useRef(null);

  useEffect(() => {
    if (!user) return;
    setForm((p) => ({
      ...p,
      owner_name: p.owner_name || user.name,
      owner_phone: p.owner_phone || user.phone || "",
      owner_email: p.owner_email || user.email,
    }));
  }, [user]);

  function handleChange(e) {
    const { name, value, type, checked } = e.target;
    setForm((prev) => ({ ...prev, [name]: type === "checkbox" ? checked : value }));
  }

  function toggleAmenity(a) {
    setForm((prev) => ({
      ...prev,
      amenities: prev.amenities.includes(a)
        ? prev.amenities.filter((x) => x !== a)
        : [...prev.amenities, a],
    }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const payload = {
        ...form,
        price: parseFloat(form.price),
        bedrooms: parseInt(form.bedrooms),
        bathrooms: parseInt(form.bathrooms),
        area_sqft: form.area_sqft ? parseFloat(form.area_sqft) : null,
        university_distance_km: form.university_distance_km ? parseFloat(form.university_distance_km) : null,
        safety_score: form.safety_score ? parseFloat(form.safety_score) : null,
        nearby_university: form.nearby_university || null,
        owner_email: form.owner_email || null,
        rental_type: form.listing_type === "sale" ? null : form.rental_type,
        photos: [],
        documents: [],
      };
      const created = await createProperty(payload);
      setCreatedId(created.id);
      setStep(4);
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePhotoFiles(files) {
    if (!createdId || !files.length) return;
    setUploading(true);
    for (const file of Array.from(files)) {
      try {
        const result = await uploadPhoto(createdId, file);
        setPhotos((prev) => [...prev, { url: `${API_ROOT}${result.url}`, name: file.name }]);
      } catch {
        // skip failed uploads silently — user can retry
      }
    }
    setUploading(false);
  }

  async function handleDocFiles(files) {
    if (!createdId || !files.length) return;
    setUploading(true);
    for (const file of Array.from(files)) {
      try {
        const result = await uploadDocument(createdId, file);
        setDocuments((prev) => [...prev, { url: `${API_ROOT}${result.url}`, name: result.name }]);
      } catch {
        // skip failed uploads silently — user can retry
      }
    }
    setUploading(false);
  }

  function handleDrop(e, type) {
    e.preventDefault();
    const files = e.dataTransfer.files;
    type === "photo" ? handlePhotoFiles(files) : handleDocFiles(files);
  }

  const isSale = form.listing_type === "sale";

  return (
    <div className="lp-layout">
      <nav className="browse-nav">
        <Link to="/" className="nav-logo">bari<span>.com</span></Link>
        <div className="browse-nav-right">
          <NavAuth />
          <Link to="/browse" className="back-link">← Browse listings</Link>
        </div>
      </nav>

      <div className="lp-container">
        <div className="lp-header">
          <h1>List Your Property</h1>
          <p>Fill in the details below and your listing will appear on bari.com within minutes.</p>
        </div>
        {ready && (!user || !["owner", "admin"].includes(user.role)) && (
          <div className="auth-gate" style={{ marginBottom: "1.5rem" }}>
            {user ? "Your account is a renter account. Listing a property needs an owner account." : "Log in with an owner account to list a property."}
            <br />
            <button onClick={() => openAuth({ mode: user ? "signup" : "login", role: "owner", reason: "Owner accounts can list properties." })}>
              {user ? "Create an owner account" : "Log in"}
            </button>
          </div>
        )}

        <div className="lp-steps">
          {STEPS.map((label, i) => (
            <button
              key={label}
              type="button"
              className={`lp-step-btn${step === i + 1 ? " active" : step > i + 1 ? " done" : ""}`}
              onClick={() => i + 1 < 4 && step !== 4 && setStep(i + 1)}
              disabled={i + 1 === 4 && !createdId}
            >
              <span className="step-num">{step > i + 1 ? "✓" : i + 1}</span>
              {label}
            </button>
          ))}
        </div>

        <div className={`lp-body${step < 4 ? " with-assistant" : ""}`}>
        <form onSubmit={handleSubmit} className="lp-form">

          {/* ── Step 1: Property Details ── */}
          {step === 1 && (
            <div className="lp-section">
              <h2>Property Details</h2>

              <div className="lp-field">
                <label>Listing title *</label>
                <input name="title" value={form.title} onChange={handleChange} required
                  placeholder="e.g. Furnished 2-bed flat near BRAC University" />
              </div>

              <div className="lp-field">
                <label>Description *</label>
                <textarea name="description" value={form.description} onChange={handleChange} required
                  rows={4} placeholder="Describe the property — size, floor, surroundings, special features…" />
              </div>

              <div className="lp-row">
                <div className="lp-field">
                  <label>Property type *</label>
                  <select name="property_type" value={form.property_type} onChange={handleChange}>
                    {["apartment", "house", "office", "room"].map((t) => (
                      <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                    ))}
                  </select>
                </div>
                <div className="lp-field">
                  <label>Listing type *</label>
                  <select name="listing_type" value={form.listing_type} onChange={handleChange}>
                    {["rent", "sale", "sublet"].map((t) => (
                      <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                    ))}
                  </select>
                </div>
              </div>

              {!isSale && (
                <div className="lp-field">
                  <label>Rental period *</label>
                  <div className="lp-radio-group">
                    {["monthly", "daily", "hourly"].map((r) => (
                      <label key={r} className="radio-option">
                        <input type="radio" name="rental_type" value={r}
                          checked={form.rental_type === r} onChange={handleChange} />
                        {r.charAt(0).toUpperCase() + r.slice(1)}
                      </label>
                    ))}
                  </div>
                </div>
              )}

              <div className="lp-row">
                <div className="lp-field">
                  <label>Furnishing *</label>
                  <select name="furnishing" value={form.furnishing} onChange={handleChange}>
                    {["furnished", "semi_furnished", "unfurnished"].map((f) => (
                      <option key={f} value={f}>{f.replace("_", " ")}</option>
                    ))}
                  </select>
                </div>
                <div className="lp-field">
                  <label>Price (৳){!isSale && " per period"} *</label>
                  <input name="price" type="number" value={form.price} onChange={handleChange}
                    required min="1" placeholder={isSale ? "e.g. 8500000" : "e.g. 12000"} />
                </div>
              </div>

              <div className="lp-row">
                <div className="lp-field">
                  <label>Bedrooms</label>
                  <select name="bedrooms" value={form.bedrooms} onChange={handleChange}>
                    {[0, 1, 2, 3, 4, 5].map((n) => (
                      <option key={n} value={n}>{n === 0 ? "Studio / N/A" : n}</option>
                    ))}
                  </select>
                </div>
                <div className="lp-field">
                  <label>Bathrooms</label>
                  <select name="bathrooms" value={form.bathrooms} onChange={handleChange}>
                    {[1, 2, 3, 4].map((n) => (
                      <option key={n} value={n}>{n}</option>
                    ))}
                  </select>
                </div>
                <div className="lp-field">
                  <label>Area (sqft)</label>
                  <input name="area_sqft" type="number" value={form.area_sqft} onChange={handleChange}
                    placeholder="Optional" />
                </div>
              </div>

              <div className="lp-field">
                <label>Amenities</label>
                <div className="amenity-picker">
                  {AMENITY_OPTIONS.map((a) => (
                    <button key={a} type="button"
                      className={`amenity-pill${form.amenities.includes(a) ? " selected" : ""}`}
                      onClick={() => toggleAmenity(a)}>
                      {a}
                    </button>
                  ))}
                </div>
              </div>

              <div className="lp-checks">
                <label className="check-option">
                  <input type="checkbox" name="is_female_only" checked={form.is_female_only} onChange={handleChange} />
                  Women-only listing (female students only)
                </label>
                <label className="check-option">
                  <input type="checkbox" name="has_furniture_for_sale" checked={form.has_furniture_for_sale} onChange={handleChange} />
                  Furniture available for sale with this rental
                </label>
              </div>

              <div className="lp-nav">
                <span />
                <button type="button" className="btn-next" onClick={() => setStep(2)}>
                  Next: Location →
                </button>
              </div>
            </div>
          )}

          {/* ── Step 2: Location ── */}
          {step === 2 && (
            <div className="lp-section">
              <h2>Location & University</h2>

              <div className="lp-field">
                <label>Full address *</label>
                <input name="address" value={form.address} onChange={handleChange} required
                  placeholder="House/Road/Block, e.g. House 12, Road 7, Dhanmondi" />
              </div>

              <div className="lp-row">
                <div className="lp-field">
                  <label>Neighborhood / Area *</label>
                  <input name="area" value={form.area} onChange={handleChange} required
                    placeholder="e.g. Gulshan, Mirpur, Dhanmondi" />
                </div>
                <div className="lp-field">
                  <label>City *</label>
                  <input name="city" value={form.city} onChange={handleChange} required />
                </div>
              </div>

              <div className="lp-row">
                <div className="lp-field">
                  <label>Nearby university</label>
                  <select name="nearby_university" value={form.nearby_university} onChange={handleChange}>
                    <option value="">Not applicable</option>
                    {UNIVERSITIES.map((u) => <option key={u} value={u}>{u}</option>)}
                  </select>
                </div>
                <div className="lp-field">
                  <label>Distance to university (km)</label>
                  <input name="university_distance_km" type="number" step="0.1"
                    value={form.university_distance_km} onChange={handleChange}
                    placeholder="e.g. 0.8" disabled={!form.nearby_university} />
                </div>
              </div>

              <div className="lp-field">
                <label>Safety score (0–5)</label>
                <input name="safety_score" type="number" step="0.1" min="0" max="5"
                  value={form.safety_score} onChange={handleChange} placeholder="Optional — e.g. 4.5" />
                <span className="field-hint">You can leave this blank — renters can add community safety scores later.</span>
              </div>

              <div className="lp-nav">
                <button type="button" className="btn-back" onClick={() => setStep(1)}>← Back</button>
                <button type="button" className="btn-next" onClick={() => setStep(3)}>
                  Next: Owner Info →
                </button>
              </div>
            </div>
          )}

          {/* ── Step 3: Owner Details + Submit ── */}
          {step === 3 && (
            <div className="lp-section">
              <h2>Your Contact Details</h2>
              <p className="lp-note">These details will be shown to interested renters/buyers on your listing.</p>

              <div className="lp-field">
                <label>Your name *</label>
                <input name="owner_name" value={form.owner_name} onChange={handleChange}
                  required placeholder="Full name" />
              </div>

              <div className="lp-row">
                <div className="lp-field">
                  <label>Phone number *</label>
                  <input name="owner_phone" value={form.owner_phone} onChange={handleChange}
                    required placeholder="01XXXXXXXXX" />
                </div>
                <div className="lp-field">
                  <label>Email (optional)</label>
                  <input name="owner_email" type="email" value={form.owner_email} onChange={handleChange}
                    placeholder="you@example.com" />
                </div>
              </div>

              {error && (
                <div className="lp-error">
                  <strong>Submission failed:</strong> {error}
                </div>
              )}

              <div className="lp-nav">
                <button type="button" className="btn-back" onClick={() => setStep(2)}>← Back</button>
                <button type="submit" className="btn-submit" disabled={submitting}>
                  {submitting ? "Publishing…" : "Publish & Add Photos →"}
                </button>
              </div>
            </div>
          )}

          {/* ── Step 4: Photos & Documents ── */}
          {step === 4 && (
            <div className="lp-section">
              <div className="step4-success">
                <span className="step4-check">✓</span>
                <div>
                  <strong>Listing published!</strong>
                  <span>Now add photos and ownership documents to boost trust with renters.</span>
                </div>
              </div>
              <p className="lp-review-note">
                Every new listing is automatically checked for duplicates and scam patterns. If something looks off,
                it's held for a quick review and you'll see the reason under your listings.
              </p>

              {/* Photos */}
              <h2>Property Photos</h2>
              <p className="lp-note">Upload JPEG, PNG, or WebP images. You can add multiple.</p>

              <div
                className="upload-dropzone"
                onClick={() => photoInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => handleDrop(e, "photo")}
              >
                <input
                  ref={photoInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  multiple
                  className="upload-input-hidden"
                  onChange={(e) => handlePhotoFiles(e.target.files)}
                />
                <div className="dropzone-icon">📷</div>
                <p>Drag photos here or <span className="dropzone-link">click to browse</span></p>
                <span className="field-hint">JPEG · PNG · WebP</span>
              </div>

              {photos.length > 0 && (
                <div className="upload-preview-grid">
                  {photos.map((p, i) => (
                    <div key={i} className="upload-thumb">
                      <img src={p.url} alt={p.name} />
                    </div>
                  ))}
                </div>
              )}

              {/* Documents */}
              <h2 style={{ marginTop: "2rem" }}>Ownership Documents</h2>
              <p className="lp-note">Upload proof of ownership or tenancy agreement (PDF or image). Required for admin verification.</p>

              <div
                className="upload-dropzone upload-dropzone-doc"
                onClick={() => docInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => handleDrop(e, "doc")}
              >
                <input
                  ref={docInputRef}
                  type="file"
                  accept="application/pdf,image/jpeg,image/png,image/webp"
                  multiple
                  className="upload-input-hidden"
                  onChange={(e) => handleDocFiles(e.target.files)}
                />
                <div className="dropzone-icon">📄</div>
                <p>Drag documents here or <span className="dropzone-link">click to browse</span></p>
                <span className="field-hint">PDF · JPEG · PNG · WebP</span>
              </div>

              {documents.length > 0 && (
                <ul className="doc-list">
                  {documents.map((d, i) => (
                    <li key={i} className="doc-item">
                      <span className="doc-icon">📄</span>
                      <a href={d.url} target="_blank" rel="noreferrer">{d.name}</a>
                    </li>
                  ))}
                </ul>
              )}

              {uploading && <p className="upload-status">Uploading…</p>}

              <div className="lp-nav" style={{ marginTop: "2rem" }}>
                <span className="field-hint">
                  {photos.length} photo{photos.length !== 1 ? "s" : ""} · {documents.length} document{documents.length !== 1 ? "s" : ""} uploaded
                </span>
                <button
                  type="button"
                  className="btn-submit"
                  onClick={() => navigate(`/property/${createdId}`)}
                  disabled={uploading}
                >
                  View Listing →
                </button>
              </div>
            </div>
          )}

        </form>
        {step < 4 && (
          <ListingAssistant form={form} photos={photos}
            onUseDescription={(d) => { setForm((p) => ({ ...p, description: d })); setStep(1); }} />
        )}
        </div>
      </div>
    </div>
  );
}

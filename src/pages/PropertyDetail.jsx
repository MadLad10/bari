import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { fetchProperty } from "../api";
import BookingPanel from "../components/BookingPanel";
import ChatWidget from "../components/ChatWidget";
import SafetySection from "../components/SafetySection";
import NavAuth from "../auth/NavAuth";
import { API_ROOT } from "../api";
import "./PropertyDetail.css";

const LABEL = {
  apartment: "Apartment",
  house: "House",
  office: "Office",
  room: "Room",
  rent: "For Rent",
  sale: "For Sale",
  sublet: "Sublet",
  furnished: "Furnished",
  semi_furnished: "Semi-furnished",
  unfurnished: "Unfurnished",
  monthly: "/month",
  daily: "/day",
  hourly: "/hour",
};

export default function PropertyDetail() {
  const { id } = useParams();
  const [property, setProperty] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activePhoto, setActivePhoto] = useState(0);

  useEffect(() => {
    fetchProperty(id)
      .then(setProperty)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <DetailSkeleton />;
  if (error) return (
    <div className="detail-error">
      <p>Property not found.</p>
      <Link to="/browse">Back to browse</Link>
    </div>
  );

  const { title, description, property_type, listing_type, rental_type,
    furnishing, price, bedrooms, bathrooms, area_sqft,
    address, area, city, nearby_university, university_distance_km,
    is_female_only, safety_score, amenities, photos,
    has_furniture_for_sale, owner_name, owner_phone, owner_email,
    created_at } = property;

  const priceLabel = listing_type === "sale"
    ? `৳${Number(price).toLocaleString()}`
    : `৳${Number(price).toLocaleString()}${LABEL[rental_type] || ""}`;

  return (
    <div className="detail-layout">
      <nav className="browse-nav">
        <Link to="/" className="nav-logo">bari<span>.com</span></Link>
        <div className="browse-nav-right">
          <NavAuth />
          <Link to="/browse" className="back-link">← Back to listings</Link>
          <Link to="/list-property" className="nav-cta">List Your Property</Link>
        </div>
      </nav>

      <div className="detail-container">
        {/* Photos */}
        <div className="detail-photos">
          <div className="photo-main">
            {photos.length > 0 ? (
              <img src={`${API_ROOT}${photos[activePhoto]}`} alt={title} />
            ) : (
              <div className="photo-placeholder">
                <span>{LABEL[property_type]}</span>
              </div>
            )}
          </div>
          {photos.length > 1 && (
            <div className="photo-thumbs">
              {photos.map((p, i) => (
                <button key={i} className={`photo-thumb${activePhoto === i ? " active" : ""}`}
                  onClick={() => setActivePhoto(i)}>
                  <img src={`${API_ROOT}${p}`} alt={`Photo ${i + 1}`} />
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="detail-body">
          <div className="detail-main">
            {/* Badges */}
            <div className="detail-badges">
              {property.document_check_status === "passed" && <span className="d-badge">Document checks passed</span>}
              {property.document_check_status === "reviewed" && <span className="d-badge">Documents reviewed by admin</span>}
              <span className="d-badge">{LABEL[listing_type]}</span>
              <span className="d-badge">{LABEL[property_type]}</span>
              {is_female_only && <span className="d-badge d-badge-female">{property.women_safety_status === "approved" ? "Women only · Safety review approved" : "Women only · Awaiting safety approval"}</span>}
              {has_furniture_for_sale && <span className="d-badge d-badge-furn">Furniture for sale</span>}
            </div>

            <h1 className="detail-title">{title}</h1>
            {is_female_only && property.women_safety_status === "approved" && <p>Admin safety review completed {property.women_safety_reviewed_at ? new Date(property.women_safety_reviewed_at).toLocaleDateString("en-BD") : ""}. This records a review of evidence and does not guarantee safety.</p>}
            {property.status !== "active" && <p role="status">This listing is hidden from public browsing while it awaits checks or review.</p>}
            <div className="detail-location">{address}, {area}, {city}</div>
            <div className="detail-price">{priceLabel}</div>

            {/* Key stats */}
            <div className="detail-stats">
              {bedrooms > 0 && (
                <div className="stat-box">
                  <div className="stat-val">{bedrooms}</div>
                  <div className="stat-lbl">Bedroom{bedrooms !== 1 ? "s" : ""}</div>
                </div>
              )}
              {bathrooms > 0 && (
                <div className="stat-box">
                  <div className="stat-val">{bathrooms}</div>
                  <div className="stat-lbl">Bathroom{bathrooms !== 1 ? "s" : ""}</div>
                </div>
              )}
              {area_sqft && (
                <div className="stat-box">
                  <div className="stat-val">{area_sqft}</div>
                  <div className="stat-lbl">sqft</div>
                </div>
              )}
              {safety_score && (
                <div className="stat-box stat-box-safety">
                  <div className="stat-val">{safety_score}</div>
                  <div className="stat-lbl">Safety</div>
                </div>
              )}
            </div>

            {/* University proximity */}
            {nearby_university && (
              <div className="detail-uni">
                <span className="uni-icon">🎓</span>
                <span>{university_distance_km?.toFixed(1)} km from {nearby_university}</span>
              </div>
            )}

            {/* Furnishing */}
            <div className="detail-section">
              <h2>Details</h2>
              <div className="detail-rows">
                <div className="detail-row">
                  <span>Furnishing</span>
                  <span>{LABEL[furnishing]}</span>
                </div>
                <div className="detail-row">
                  <span>Type</span>
                  <span>{LABEL[property_type]}</span>
                </div>
                <div className="detail-row">
                  <span>Listing</span>
                  <span>{LABEL[listing_type]}</span>
                </div>
                {rental_type && (
                  <div className="detail-row">
                    <span>Rental period</span>
                    <span>{rental_type.charAt(0).toUpperCase() + rental_type.slice(1)}</span>
                  </div>
                )}
                <div className="detail-row">
                  <span>Listed</span>
                  <span>{new Date(created_at).toLocaleDateString("en-BD", { dateStyle: "medium" })}</span>
                </div>
              </div>
            </div>

            {/* Description */}
            <div className="detail-section">
              <h2>Description</h2>
              <p className="detail-desc">{description}</p>
            </div>

            {/* Amenities */}
            {amenities?.length > 0 && (
              <div className="detail-section">
                <h2>Amenities</h2>
                <div className="amenity-list">
                  {amenities.map((a) => (
                    <span key={a} className="amenity-tag">{a}</span>
                  ))}
                </div>
              </div>
            )}

            {/* Map + Safety */}
            <SafetySection property={property} />

            {/* Report */}
            <div className="detail-section">
              <Link to={`/reports/new?property_id=${property.id}`} className="report-link">
                ⚑ Report this listing as unsafe
              </Link>
            </div>
          </div>

          {/* Sidebar: owner + booking + chat */}
          <aside className="detail-aside">
            <div className="owner-card">
              <div className="owner-avatar">{owner_name.charAt(0)}</div>
              <div className="owner-name">{owner_name}</div>
              <div className="owner-label">Property Owner</div>
              <a href={`tel:${owner_phone}`} className="owner-btn owner-btn-call">
                Call {owner_phone}
              </a>
              {owner_email && (
                <a href={`mailto:${owner_email}`} className="owner-btn owner-btn-email">
                  Send Email
                </a>
              )}
            </div>

            <BookingPanel property={property} />
            <ChatWidget property={property} />
          </aside>
        </div>
      </div>
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="detail-layout">
      <nav className="browse-nav">
        <Link to="/" className="nav-logo">bari<span>.com</span></Link>
      </nav>
      <div className="detail-container">
        <div className="photo-placeholder detail-skeleton-photo" />
        <div className="detail-body">
          <div className="detail-main">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="skeleton-line" style={{ width: `${80 - i * 10}%`, height: i === 0 ? 32 : 18, marginBottom: 12, borderRadius: 6, background: "#e8e8e4", animation: "shimmer 1.4s infinite" }} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

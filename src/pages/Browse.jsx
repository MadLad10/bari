import { useState, useEffect, useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { fetchProperties } from "../api";
import AIAssistant from "../components/AIAssistant";
import NavAuth from "../auth/NavAuth";
import { API_ROOT } from "../api";
import "./Browse.css";

const UNIVERSITIES = [
  "BRAC University",
  "North South University",
  "BUET",
  "Dhaka University",
  "Jahangirnagar University",
  "IUT",
  "AIUB",
  "BRAC",
  "AUST",
];

const PROPERTY_TYPES = ["apartment", "house", "office", "room"];
const LISTING_TYPES = ["rent", "sale", "sublet"];
const FURNISHINGS = ["furnished", "semi_furnished", "unfurnished"];

function PropertyCard({ property }) {
  const photo = property.photos?.[0];
  const priceLabel =
    property.listing_type === "sale"
      ? `৳${Number(property.price).toLocaleString()}`
      : property.rental_type === "hourly"
        ? `৳${Number(property.price).toLocaleString()}/hr`
        : property.rental_type === "daily"
          ? `৳${Number(property.price).toLocaleString()}/day`
          : `৳${Number(property.price).toLocaleString()}/mo`;

  return (
    <Link to={`/property/${property.id}`} className="prop-card">
      <div className="prop-card-img">
        {photo ? (
          <img src={`${API_ROOT}${photo}`} alt={property.title} />
        ) : (
          <div className="prop-card-img-placeholder">
            <span>{property.property_type}</span>
          </div>
        )}
        {property.is_female_only && (
          <span className="badge-female">Women Only</span>
        )}
        {property.listing_type === "sublet" && (
          <span className="badge-sublet">Sublet</span>
        )}
      </div>
      <div className="prop-card-body">
        <div className="prop-card-price">{priceLabel}</div>
        <h3 className="prop-card-title">{property.title}</h3>
        <div className="prop-card-meta">
          <span>{property.area}, {property.city}</span>
          {property.bedrooms > 0 && (
            <span>{property.bedrooms} bed · {property.bathrooms} bath</span>
          )}
        </div>
        {property.nearby_university && (
          <div className="prop-card-uni">
            {property.university_distance_km?.toFixed(1)} km · {property.nearby_university}
          </div>
        )}
        <div className="prop-card-tags">
          <span className="tag">{property.furnishing.replace("_", " ")}</span>
          {property.safety_score && (
            <span className="tag tag-safety">Safety {property.safety_score}</span>
          )}
        </div>
      </div>
    </Link>
  );
}

export default function Browse() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [properties, setProperties] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [filters, setFilters] = useState({
    q: searchParams.get("q") || "",
    listing_type: searchParams.get("listing_type") || "",
    property_type: searchParams.get("property_type") || "",
    furnishing: searchParams.get("furnishing") || "",
    min_price: searchParams.get("min_price") || "",
    max_price: searchParams.get("max_price") || "",
    bedrooms: searchParams.get("bedrooms") || "",
    nearby_university: searchParams.get("nearby_university") || "",
    is_female_only: searchParams.get("is_female_only") || "",
  });

  const load = useCallback(async (f) => {
    setLoading(true);
    setError(null);
    try {
      const params = { ...f };
      if (params.is_female_only === "") delete params.is_female_only;
      const data = await fetchProperties(params);
      setProperties(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(filters);
  }, []);

  function handleChange(e) {
    setFilters((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  function handleSubmit(e) {
    e.preventDefault();
    const params = {};
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== "") params[k] = v;
    });
    setSearchParams(params);
    load(filters);
  }

  function handleReset() {
    const cleared = {
      q: "", listing_type: "", property_type: "", furnishing: "",
      min_price: "", max_price: "", bedrooms: "", nearby_university: "", is_female_only: "",
    };
    setFilters(cleared);
    setSearchParams({});
    load(cleared);
  }

  const activeTab = filters.listing_type;

  return (
    <div className="browse-layout">
      <nav className="browse-nav">
        <Link to="/" className="nav-logo">bari<span>.com</span></Link>
        <div className="browse-nav-right">
          <NavAuth />
          <Link to="/list-property" className="nav-cta">List Your Property</Link>
        </div>
      </nav>

      <div className="browse-body">
        <aside className="browse-sidebar">
          <h2>Filters</h2>
          <form onSubmit={handleSubmit} className="filter-form">
            <div className="filter-group">
              <label>Search</label>
              <input
                name="q"
                value={filters.q}
                onChange={handleChange}
                placeholder="Area, title, description…"
              />
            </div>

            <div className="filter-group">
              <label>Listing type</label>
              <div className="tab-group">
                {["", ...LISTING_TYPES].map((t) => (
                  <button
                    key={t}
                    type="button"
                    className={`tab-btn${filters.listing_type === t ? " active" : ""}`}
                    onClick={() => setFilters((p) => ({ ...p, listing_type: t }))}
                  >
                    {t === "" ? "All" : t.charAt(0).toUpperCase() + t.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            <div className="filter-group">
              <label>Property type</label>
              <select name="property_type" value={filters.property_type} onChange={handleChange}>
                <option value="">Any</option>
                {PROPERTY_TYPES.map((t) => (
                  <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                ))}
              </select>
            </div>

            <div className="filter-group">
              <label>Furnishing</label>
              <select name="furnishing" value={filters.furnishing} onChange={handleChange}>
                <option value="">Any</option>
                {FURNISHINGS.map((f) => (
                  <option key={f} value={f}>{f.replace("_", " ")}</option>
                ))}
              </select>
            </div>

            <div className="filter-group">
              <label>Price (৳)</label>
              <div className="price-range">
                <input name="min_price" value={filters.min_price} onChange={handleChange} type="number" placeholder="Min" />
                <span>–</span>
                <input name="max_price" value={filters.max_price} onChange={handleChange} type="number" placeholder="Max" />
              </div>
            </div>

            <div className="filter-group">
              <label>Min bedrooms</label>
              <select name="bedrooms" value={filters.bedrooms} onChange={handleChange}>
                <option value="">Any</option>
                {[1, 2, 3, 4].map((n) => (
                  <option key={n} value={n}>{n}+</option>
                ))}
              </select>
            </div>

            <div className="filter-group">
              <label>Near university</label>
              <select name="nearby_university" value={filters.nearby_university} onChange={handleChange}>
                <option value="">Any</option>
                {UNIVERSITIES.map((u) => (
                  <option key={u} value={u}>{u}</option>
                ))}
              </select>
            </div>

            <div className="filter-group filter-group-check">
              <label>
                <input
                  type="checkbox"
                  checked={filters.is_female_only === "true"}
                  onChange={(e) =>
                    setFilters((p) => ({ ...p, is_female_only: e.target.checked ? "true" : "" }))
                  }
                />
                Women-only listings
              </label>
            </div>

            <div className="filter-actions">
              <button type="submit" className="btn-filter-apply">Apply</button>
              <button type="button" className="btn-filter-reset" onClick={handleReset}>Reset</button>
            </div>
          </form>
        </aside>

        <main className="browse-main">
          <div className="browse-header">
            <h1>
              {activeTab === "sublet" ? "Student Sublets"
                : activeTab === "sale" ? "Properties for Sale"
                : activeTab === "rent" ? "Properties for Rent"
                : "All Listings"}
            </h1>
            {!loading && (
              <span className="result-count">{properties.length} result{properties.length !== 1 ? "s" : ""}</span>
            )}
          </div>

          {loading && (
            <div className="browse-loading">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="prop-card-skeleton" />
              ))}
            </div>
          )}

          {error && (
            <div className="browse-error">
              <p>Could not load properties. Make sure the backend is running.</p>
              <code>{error}</code>
            </div>
          )}

          {!loading && !error && properties.length === 0 && (
            <div className="browse-empty">
              <p>No properties match your filters.</p>
              <button className="btn-filter-reset" onClick={handleReset}>Clear filters</button>
            </div>
          )}

          {!loading && !error && properties.length > 0 && (
            <div className="prop-grid">
              {properties.map((p) => (
                <PropertyCard key={p.id} property={p} />
              ))}
            </div>
          )}
        </main>
      </div>
      <AIAssistant />
    </div>
  );
}

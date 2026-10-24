import { useState, useEffect, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { fetchProperties, countProperties, fetchPropertyMap } from "../api";
import GeoMap from "../components/GeoMap";
import { photoUrl } from "../components/OwnerPhotos";
import AIAssistant from "../components/AIAssistant";
import NavAuth from "../auth/NavAuth";
import "./Browse.css";

const UNIVERSITIES = [
  "BRAC University",
  "North South University",
  "Dhaka University",
  "BUET",
  "IUB",
  "AIUB",
  "East West University",
  "Jahangirnagar University",
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
          <img src={photoUrl(photo)} alt={property.title} />
        ) : (
          <div className="prop-card-img-placeholder">
            <span>{property.property_type}</span>
          </div>
        )}
        {property.is_female_only && (
            <span className="badge-female" title="Separate admin safety review completed. This is not a guarantee of safety.">Women only · Admin reviewed</span>
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

const FILTER_KEYS = ["q", "listing_type", "property_type", "furnishing", "min_price", "max_price", "bedrooms", "nearby_university", "is_female_only", "min_safety_score", "max_university_distance_km", "rental_type"];
const PAGE_SIZE = 20;
const readFilters = params => Object.fromEntries(FILTER_KEYS.map(key => [key, params.get(key) || ""]));

export default function Browse() {
  const [searchParams, setSearchParams] = useSearchParams();
  const serialized = searchParams.toString();
  const applied = useMemo(() => readFilters(new URLSearchParams(serialized)), [serialized]);
  const rawPage = Number(searchParams.get("page") || 1);
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 && rawPage <= 1000000 ? rawPage : 1;
  const view = searchParams.get("view") === "map" ? "map" : "list";
  const [filters, setFilters] = useState(applied);
  const [properties, setProperties] = useState([]), [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true), [error, setError] = useState(null);
  const [mapData, setMapData] = useState(null), [mapLoading, setMapLoading] = useState(false), [mapError, setMapError] = useState("");
  useEffect(() => { setFilters(applied); }, [applied]);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(null);
    Promise.all([fetchProperties({ ...applied, skip: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE }), countProperties(applied)])
      .then(([rows, result]) => {
        if (!active) return;
        const pages = Math.max(1, Math.ceil(result.count / PAGE_SIZE));
        if (page > pages) { const next = new URLSearchParams(serialized); if (pages === 1) next.delete("page"); else next.set("page", pages); setSearchParams(next, { replace: true }); return; }
        setProperties(rows); setTotal(result.count);
      }).catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [applied, page, serialized, setSearchParams]);
  useEffect(() => {
    if (view !== "map") return;
    let active = true;
    setMapData(null); setMapLoading(true); setMapError("");
    fetchPropertyMap(applied).then(result => { if (active) setMapData(result); }).catch(e => { if (active) setMapError(e.message); }).finally(() => { if (active) setMapLoading(false); });
    return () => { active = false; };
  }, [applied, view]);
  const mapPoints = useMemo(() => (mapData?.items || []).map(p => ({ ...p, propertyId: p.id })), [mapData]);
  function handleChange(e) { setFilters(prev => ({ ...prev, [e.target.name]: e.target.value })); }
  function handleSubmit(e) {
    e.preventDefault();
    const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== ""));
    if (view === "map") params.view = "map";
    setSearchParams(params);
  }
  function handleReset() { setSearchParams(view === "map" ? { view: "map" } : {}); setFilters(readFilters(new URLSearchParams())); }
  function changePage(nextPage) { const next = new URLSearchParams(serialized); if (nextPage === 1) next.delete("page"); else next.set("page", nextPage); setSearchParams(next); }
  function changeView(nextView) { const next = new URLSearchParams(serialized); if (nextView === "list") next.delete("view"); else next.set("view", "map"); setSearchParams(next); }
  const activeTab = applied.listing_type;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

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
              <label htmlFor="browse-search">Search</label>
              <input
                id="browse-search" name="q"
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
              <label htmlFor="browse-property_type">Property type</label>
              <select id="browse-property_type" name="property_type" value={filters.property_type} onChange={handleChange}>
                <option value="">Any</option>
                {PROPERTY_TYPES.map((t) => (
                  <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                ))}
              </select>
            </div>

            <div className="filter-group">
              <label htmlFor="browse-furnishing">Furnishing</label>
              <select id="browse-furnishing" name="furnishing" value={filters.furnishing} onChange={handleChange}>
                <option value="">Any</option>
                {FURNISHINGS.map((f) => (
                  <option key={f} value={f}>{f.replace("_", " ")}</option>
                ))}
              </select>
            </div>

            <div className="filter-group">
              <label>Price (৳)</label>
              <div className="price-range">
                <input aria-label="Minimum price" min="0" name="min_price" value={filters.min_price} onChange={handleChange} type="number" placeholder="Min" />
                <span>–</span>
                <input aria-label="Maximum price" min="0" name="max_price" value={filters.max_price} onChange={handleChange} type="number" placeholder="Max" />
              </div>
            </div>

            <div className="filter-group">
              <label htmlFor="browse-bedrooms">Min bedrooms</label>
              <select id="browse-bedrooms" name="bedrooms" value={filters.bedrooms} onChange={handleChange}>
                <option value="">Any</option>
                {[1, 2, 3, 4].map((n) => (
                  <option key={n} value={n}>{n}+</option>
                ))}
              </select>
            </div>

            <div className="filter-group">
              <label htmlFor="browse-nearby_university">Near university</label>
              <select id="browse-nearby_university" name="nearby_university" value={filters.nearby_university} onChange={handleChange}>
                <option value="">Any</option>
                {UNIVERSITIES.map((u) => (
                  <option key={u} value={u}>{u}</option>
                ))}
              </select>
            </div>

            <div className="filter-group"><label htmlFor="browse-period">Rental period</label><select id="browse-period" name="rental_type" value={filters.rental_type} onChange={handleChange}><option value="">Any period</option><option value="hourly">Hourly</option><option value="daily">Daily</option><option value="monthly">Monthly</option></select></div>
            <div className="filter-group"><label htmlFor="browse-safety">Minimum safety rating</label><select id="browse-safety" name="min_safety_score" value={filters.min_safety_score} onChange={handleChange}><option value="">Any rating</option>{[1, 2, 3, 4, 4.5, 5].map(value => <option key={value} value={value}>{value}+ / 5</option>)}</select></div>
            <div className="filter-group"><label htmlFor="browse-distance">Maximum campus distance (km)</label><input id="browse-distance" name="max_university_distance_km" type="number" min="0" step="0.1" placeholder="Any distance" value={filters.max_university_distance_km} onChange={handleChange} /></div>
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
              <span className="result-count" role="status">{view === "map" ? `${total} matching listings` : total ? `${(page - 1) * PAGE_SIZE + 1}-${Math.min(page * PAGE_SIZE, total)} of ${total} listings` : "0 listings"}</span>
            )}
          </div>

          <div className="browse-view-controls"><button type="button" aria-pressed={view === "list"} onClick={() => changeView("list")}>List view</button><button type="button" aria-pressed={view === "map"} onClick={() => changeView("map")}>Map view</button></div>
          {view === "map" && <section className="browse-map-panel" aria-label="Matching property locations">
            {mapLoading && <p role="status">Loading matching map pins?</p>}{mapError && <p role="alert" className="geo-error">{mapError}</p>}
            {mapData && <><GeoMap points={mapPoints} label="All matching property pins" /><p className="geo-help">{mapPoints.length} pins across all matching pages. {mapData.missing_coordinates > 0 && `${mapData.missing_coordinates} matching listings have no map pin.`} {mapData.truncated && "The map is limited to 1,000 pins; narrow the filters to see more."} Select a pin to open its listing.</p></>}
          </section>}

          {loading && (
            <div className="browse-loading">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="prop-card-skeleton" />
              ))}
            </div>
          )}

          {error && (
            <div className="browse-error">
              <p>Could not load properties. Try applying your filters again.</p>
              <code>{error}</code>
            </div>
          )}

          {!loading && !error && properties.length === 0 && (
            <div className="browse-empty">
              <p>No properties match your filters.</p>
              <button className="btn-filter-reset" onClick={handleReset}>Clear filters</button>
            </div>
          )}

          {!loading && !error && properties.length > 0 && view === "list" && (
            <div className="prop-grid">
              {properties.map((p) => (
                <PropertyCard key={p.id} property={p} />
              ))}
            </div>
          )}
          {!loading && !error && total > 0 && view === "list" && <nav className="browse-pagination" aria-label="Listing pages"><button disabled={page === 1} onClick={() => changePage(page - 1)}>Previous</button><label>Page<select aria-label="Listing page" value={page} onChange={e => changePage(Number(e.target.value))}>{Array.from({ length: pages }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1}</option>)}</select><span>of {pages}</span></label><button disabled={page >= pages} onClick={() => changePage(page + 1)}>Next</button></nav>}
        </main>
      </div>
      <AIAssistant />
    </div>
  );
}
